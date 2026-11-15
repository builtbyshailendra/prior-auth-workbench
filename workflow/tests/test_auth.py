"""Step 4: sign-in, sessions, service tokens, queues per person, and decisions over HTTP."""
from datetime import timedelta

import pytest

from app.auth import hash_password, make_session_token, read_session_token, verify_password
from app.clocks import clock
from tests.conftest import PASSWORD, START
from tests.helpers import payload

EXPLANATION = "Six weeks of therapy are documented but no examination findings support imaging."


def ready_case(connector, **kwargs) -> int:
    return connector.post("/api/intake", json=payload(**kwargs)).json()["case_id"]


# --- passwords and tokens --------------------------------------------------------------

def test_passwords_are_salted_scrypt_hashes():
    first, second = hash_password("correct horse"), hash_password("correct horse")
    assert first != second and first.startswith("scrypt$16384$8$1$")
    assert verify_password("correct horse", first)
    assert not verify_password("wrong horse", first)
    assert not verify_password("anything", "not-a-hash")


def test_session_tokens_expire_and_cant_be_forged(db):
    token = make_session_token("nina")
    assert read_session_token(token) == "nina"
    payload_part, signature = token.split(".")
    assert read_session_token(payload_part + "." + signature[::-1]) is None
    assert read_session_token("garbage") is None
    clock.set(START + timedelta(hours=8))
    assert read_session_token(token) is None


# --- signing in ----------------------------------------------------------------------

def test_sign_in_sets_an_http_only_cookie_and_me_reports_the_role(client):
    response = client.post("/api/auth/login", json={"username": "nina", "password": PASSWORD})
    assert response.status_code == 200
    assert response.json() == {"username": "nina", "display_name": "Nina Patel", "role": "nurse_reviewer"}
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert client.get("/api/auth/me").json()["role"] == "nurse_reviewer"


@pytest.mark.parametrize("username, password", [("nina", "wrong"), ("nobody", PASSWORD)])
def test_wrong_password_and_unknown_user_get_the_same_answer(client, username, password):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert (response.status_code, response.json()["detail"]) == (401, "Wrong username or password")


def test_five_wrong_passwords_lock_the_account_for_15_minutes(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "omar", "password": "wrong"})
    locked = client.post("/api/auth/login", json={"username": "omar", "password": PASSWORD})
    assert (locked.status_code, locked.json()["detail"]) == (429, "Too many failed attempts. Try again in 15 minutes.")
    clock.set(START + timedelta(minutes=16))
    assert client.post("/api/auth/login", json={"username": "omar", "password": PASSWORD}).status_code == 200


def test_deactivation_ends_an_existing_session(as_user):
    nina = as_user("nina")
    admin = as_user("admin")
    assert admin.post("/api/users/nina/deactivate").json()["active"] is False
    assert nina.get("/api/auth/me").status_code == 401


def test_signing_out_clears_the_cookie(as_user):
    nina = as_user("nina")
    nina.post("/api/auth/logout")
    assert nina.get("/api/auth/me").status_code == 401


def test_nothing_works_without_signing_in(client):
    assert client.get("/api/cases").status_code == 401
    assert client.post("/api/intake", json=payload()).status_code == 401


def test_cookie_requests_that_change_things_need_the_custom_header(as_user, connector):
    case_id = ready_case(connector)
    nina = as_user("nina")
    del nina.headers["X-Requested-With"]
    response = nina.post(f"/api/cases/{case_id}/start_review", json={})
    assert (response.status_code, response.json()["detail"]) == (403, "Missing X-Requested-With header")


# --- services ------------------------------------------------------------------------

def test_a_bad_api_token_is_refused(client):
    response = client.post("/api/intake", json=payload(), headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_the_extraction_service_cant_take_in_requests_or_decide(connector, client):
    case_id = ready_case(connector)
    extractor = {"Authorization": "Bearer extractor-token-for-tests-only-0001"}
    assert client.post("/api/intake", json=payload(), headers=extractor).status_code == 403
    for action in ("start_review", "approve", "deny"):
        response = client.post(f"/api/cases/{case_id}/{action}", json={"note": EXPLANATION, "reason_code": "service_not_covered"},
                               headers=extractor)
        assert response.status_code == 403, action


def test_connectors_cant_decide_or_read_queues(connector):
    case_id = ready_case(connector)
    assert connector.post(f"/api/cases/{case_id}/approve", json={}).status_code == 403
    assert connector.get("/api/cases").status_code == 403


# --- queues per person (FR-15) ------------------------------------------------------------

def test_each_role_sees_its_own_queue(connector, as_user):
    pended = ready_case(connector, member_id="SYN-M0001", documents=[])
    ready = ready_case(connector, member_id="SYN-M0002")
    nina, ivy, lee = as_user("nina"), as_user("ivy"), as_user("dr.lee")
    assert [c["id"] for c in nina.get("/api/cases").json()] == [ready]
    assert sorted(c["id"] for c in ivy.get("/api/cases").json()) == sorted([pended, ready])
    assert lee.get("/api/cases").json() == []
    assert nina.get(f"/api/cases/{pended}").status_code == 404  # not "forbidden": don't leak that it exists
    assert as_user("admin").get("/api/cases").status_code == 403


def test_a_case_under_review_leaves_the_other_nurses_queue(connector, as_user):
    case_id = ready_case(connector)
    nina, omar = as_user("nina"), as_user("omar")
    assert nina.post(f"/api/cases/{case_id}/start_review", json={}).json()["assigned_to"] == "nina"
    assert omar.get("/api/cases").json() == []
    assert omar.get(f"/api/cases/{case_id}").status_code == 404


# --- decisions over HTTP ------------------------------------------------------------------

def test_a_request_goes_from_intake_to_approval(connector, as_user):
    case_id = ready_case(connector)
    nina = as_user("nina")
    nina.post(f"/api/cases/{case_id}/start_review", json={})
    case = nina.post(f"/api/cases/{case_id}/approve", json={}).json()
    assert case["state"] == "approved"
    assert case["decision"]["by"] == "nina"
    assert [e["event"] for e in case["history"]][-2:] == ["start_review", "approve"]


def test_as10_a_nurse_cant_deny_over_the_api(connector, as_user):
    case_id = ready_case(connector)
    nina = as_user("nina")
    nina.post(f"/api/cases/{case_id}/start_review", json={})
    before = nina.get(f"/api/cases/{case_id}").json()
    response = nina.post(f"/api/cases/{case_id}/deny", json={"reason_code": "service_not_covered", "note": EXPLANATION})
    assert response.status_code == 403
    assert response.json()["detail"] == "Only a medical director can deny a case. A nurse reviewer can escalate it instead."
    assert nina.get(f"/api/cases/{case_id}").json() == before


def test_as11_a_medical_director_denies_with_a_reason(connector, as_user):
    case_id = ready_case(connector)
    nina, lee = as_user("nina"), as_user("dr.lee")
    nina.post(f"/api/cases/{case_id}/start_review", json={})
    nina.post(f"/api/cases/{case_id}/escalate", json={"note": "No exam findings documented"})
    assert lee.post(f"/api/cases/{case_id}/deny", json={"note": EXPLANATION}).status_code == 422
    case = lee.post(f"/api/cases/{case_id}/deny",
                    json={"reason_code": "documentation_does_not_support", "note": EXPLANATION}).json()
    assert case["state"] == "denied"
    assert case["decision"]["reason"] == "The documentation sent doesn't show the plan's criteria are met"
    assert case["escalation_note"] == "No exam findings documented"
    # The medical director still sees the case they decided.
    assert [c["id"] for c in lee.get("/api/cases").json()] == [case_id]


def test_wrong_state_is_a_conflict(connector, as_user):
    case_id = ready_case(connector)
    response = as_user("nina").post(f"/api/cases/{case_id}/approve", json={})
    assert response.status_code == 409


def test_an_intake_coordinator_can_enter_a_phone_request(as_user):
    ivy = as_user("ivy")
    response = ivy.post("/api/intake", json=payload(source="crm"))
    assert response.status_code == 201
    case = ivy.get(f"/api/cases/{response.json()['case_id']}").json()
    assert case["history"][0]["actor"] == "ivy"


# --- user admin --------------------------------------------------------------------------

def test_admins_manage_users_but_nobody_else_can(as_user):
    admin = as_user("admin")
    created = admin.post("/api/users", json={"username": "rosa", "display_name": "Rosa Diaz",
                                             "role": "nurse_reviewer", "password": "a-long-password"})
    assert created.status_code == 201
    assert "rosa" in [u["username"] for u in admin.get("/api/users").json()]
    assert as_user("nina").get("/api/users").status_code == 403
    assert admin.post("/api/users/admin/deactivate").status_code == 409
