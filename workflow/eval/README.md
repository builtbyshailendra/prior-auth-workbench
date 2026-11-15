# Extraction test set

40 synthetic clinical notes, each with the correct answers written down: 25 for lumbar spine MRI, 15 for a sleep study. Built by [`generate.py`](generate.py) from sentence templates whose meaning is known, so the labels can't drift from the text. Every note is fiction.

**What the extractor looks for** (illustrative, not medical policy):

| Service | Facts |
|---|---|
| Lumbar spine MRI | weeks of conservative treatment, red-flag symptoms, prior imaging, how long symptoms have lasted |
| Sleep study | Epworth score, home sleep test done, witnessed pauses in breathing |

"Not documented" is a valid answer, and the right one whenever the note doesn't say.

**Traps built into the notes:**

| Trap | Example | Right answer |
|---|---|---|
| Negation and a red flag in one sentence | "No fever, but reports new saddle numbness since Tuesday." | Red flags: yes |
| MRI only in the plan | "Plan: request MRI of the lumbar spine." | Prior imaging: not documented |
| An old score next to today's | "Epworth was 10 last year and is 16 today." | 16 |
| Nobody there to see | "Lives alone; no one has witnessed whether breathing stops at night." | Not documented (not "no") |
| Therapy recommended, never started | "...recommended at the last visit but has not been started." | 0 weeks |
| Numbers in words | "ongoing for six weeks" | 6 |
| The fact in a second document | Therapy only in the discharge summary | Found there |

## How it's scored

Every answer goes through the same checks the app uses ([`app/extraction/verify.py`](../app/extraction/verify.py)): the quote must appear in a document, numbers must appear in their quote, values must have the right type. Then each answer is compared with the label.

| Measure | Meaning |
|---|---|
| Correct | Checked answer equals the label, including "not documented" |
| Found | Of the facts the notes do contain, how many came back right |
| False fills | The note doesn't say, but a value was given. The most dangerous error |
| Wrong values | The note says one thing, the extractor another |
| Dropped | An answer failed verification and went to a person |
| Failures | The extractor errored or timed out; in the app those cases go to manual entry |

## Results

| Extractor | Correct | Found | False fills | Wrong values | Dropped | Failures | Cost |
|---|---|---|---|---|---|---|---|
| Rules baseline (regular expressions) | 110 / 145 (75.9%) | 85 / 110 (77.3%) | 10 | 9 | 0 | 0 | $0 |
| Claude Opus 5.5 | not run yet | | | | | | |

The Claude row is empty because this project has no API key yet. Anything written there would be made up. To fill it:

```bash
cd workflow
ANTHROPIC_API_KEY=... python -m eval.run --provider claude --save
```

**Expected cost** at Claude Opus 5.5 prices ($4 per million input tokens, $20 per million output):
- One note is roughly 1,500 input tokens (instructions plus note) and up to 1,000 output tokens, so about $0.03.
- The full set of 40 is about **$1 to $1.50**.

The run writes `eval/results/claude.json` with every miss, for the README.

**Where the rules baseline fails, and why it's here:**
- It reads one sentence at a time, so it misses "pain radiating to the left leg for 14 weeks".
- It counts "request MRI" in the plan as earlier imaging (6 false fills).
- It picks last year's Epworth score.
- It reads "no one has witnessed" as "no".
- It's fooled by "No fever, but reports saddle numbness".

These are the cases a language model should handle better. The test set will show whether it does, instead of anyone assuming it.
