import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { CONNECTOR_TOKEN, DEMO_PASSWORD } from "../playwright.config";

// One request from intake to a decision, as three different people, in a real browser.
// Set SCREENSHOTS=1 to also save a picture of each step into ../docs/screenshots.

const SHOTS = process.env.SCREENSHOTS ? "../docs/screenshots" : null;
const run = Date.now();
// A different service date each run, so reruns against the same database don't collide.
const day = (offset: number) => new Date(Date.UTC(2027, 0, 1) + ((run / 1000 + offset) % 300) * 86_400_000).toISOString().slice(0, 10);

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

async function signIn(page: Page, username: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();
}

async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

async function send(request: APIRequestContext, body: object): Promise<number> {
  const response = await request.post("/api/intake", {
    headers: { Authorization: `Bearer ${CONNECTOR_TOKEN}` },
    data: body,
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()).case_id;
}

function lumbarRequest() {
  return {
    source: "fax",
    source_id: `e2e-fax-${run}`,
    priority: "expedited",
    member: { id: "SYN-M0003", name: "Synthetic Member Three" },
    provider: { npi: "1234567893", name: "Synthetic Orthopedics Group" },
    service: { code: "72148", diagnosis_codes: ["M54.50"], date_start: day(0) },
    documents: [
      {
        doc_type: "clinician_note",
        title: "Clinic note",
        text: "Synthetic note. Low back pain for 10 weeks. Completed 6 weeks of physical therapy. Denies bowel or bladder changes.",
      },
      { doc_type: "conservative_treatment_record", title: "Physical therapy summary", text: "Synthetic record. 12 sessions over 6 weeks." },
    ],
  };
}

function sleepRequestWithoutDocuments() {
  return {
    source: "x12",
    source_id: `e2e-x12-${run}`,
    priority: "standard",
    member: { id: "SYN-M0004", name: "Synthetic Member Four" },
    provider: { npi: "1234567893", name: "Synthetic Sleep Clinic" },
    service: { code: "95810", diagnosis_codes: ["G47.33"], date_start: day(1) },
    documents: [],
  };
}

test("a request goes from intake to a medical director's decision", async ({ page, request }) => {
  const lumbar = await send(request, lumbarRequest());
  const sleep = await send(request, sleepRequestWithoutDocuments());

  await test.step("Intake sees the incomplete request and exactly what's missing", async () => {
    await signIn(page, "ivy");
    await expect(page.getByTestId(`case-row-${sleep}`)).toContainText("Waiting for documents");
    await page.getByTestId(`case-row-${sleep}`).getByRole("link").click();
    const missing = page.getByTestId("missing");
    await expect(missing).toContainText("Clinician note describing the sleep symptoms");
    await expect(missing).toContainText("Completed sleep questionnaire with its score");
    await shot(page, "1-intake-waiting-for-documents");
    await signOut(page);
  });

  await test.step("A nurse picks up the complete request, reads a document and escalates", async () => {
    await signIn(page, "nina");
    const row = page.getByTestId(`case-row-${lumbar}`);
    await expect(row).toContainText("Expedited");
    await expect(row).toContainText("Ready for review");
    await expect(page.getByTestId(`case-row-${sleep}`)).toHaveCount(0); // not complete, so not in a nurse's queue
    await shot(page, "2-nurse-queue");
    await row.getByRole("link").click();
    await page.getByRole("button", { name: "Clinic note" }).click();
    await expect(page.getByTestId("document-view")).toContainText("Completed 6 weeks of physical therapy");
    await page.getByRole("button", { name: "Pick up for review" }).click();
    await expect(page.getByTestId("case-state")).toHaveText("In nurse review");
    await expect(page.getByRole("button", { name: "Deny" })).toHaveCount(0); // nurses can't deny
    await page.getByLabel("Note (needed to escalate)").fill("Exam findings aren't documented; please review.");
    await page.getByRole("button", { name: "Escalate to medical director" }).click();
    await expect(page.getByTestId("case-state")).toHaveText("With medical director");
    await signOut(page);
  });

  await test.step("The medical director denies with a reason, and the history shows every step", async () => {
    await signIn(page, "dr.lee");
    await page.getByTestId(`case-row-${lumbar}`).getByRole("link").click();
    await page.getByRole("button", { name: "Deny" }).click();
    // Next.js has its own role="alert" route announcer, so pick the one with the message.
    await expect(page.getByRole("alert").filter({ hasText: "needs a reason code" })).toBeVisible();
    await page.getByLabel("Denial reason (needed to deny)").selectOption("documentation_does_not_support");
    await page.getByLabel("Explanation (needed to deny)").fill("Therapy is documented but no examination findings support imaging.");
    await page.getByRole("button", { name: "Deny" }).click();
    await expect(page.getByTestId("case-state")).toHaveText("Denied");
    await expect(page.getByTestId("decision")).toContainText("Denied by dr.lee");
    const history = page.getByTestId("history");
    for (const text of ["received the request", "picked it up for review", "escalated it to a medical director", "denied it"]) {
      await expect(history).toContainText(text);
    }
    await shot(page, "3-decided-with-history");
  });
});

test("the server refuses a decision the page doesn't offer", async ({ request }) => {
  const caseId = await send(request, { ...lumbarRequest(), source_id: `e2e-fax-b-${run}`, member: { id: "SYN-M0005", name: "x" } });
  const signIn = await request.post("/api/auth/login", { data: { username: "omar", password: DEMO_PASSWORD } });
  expect(signIn.ok()).toBeTruthy();
  const headers = { "X-Requested-With": "workbench" };
  expect((await request.post(`/api/cases/${caseId}/start_review`, { headers, data: {} })).ok()).toBeTruthy();
  const deny = await request.post(`/api/cases/${caseId}/deny`, {
    headers,
    data: { reason_code: "service_not_covered", note: "Trying to deny as a nurse, straight through the API." },
  });
  expect(deny.status()).toBe(403);
  expect((await deny.json()).detail).toBe("Only a medical director can deny a case. A nurse reviewer can escalate it instead.");
});
