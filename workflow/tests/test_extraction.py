"""Step 9: fact checking, the rules baseline and the scoring harness. No database, no API key."""
import pytest

from app.extraction.baseline import BaselineExtractor
from app.extraction.verify import RawFact, check, number_in
from eval import run as eval_run

NOTE = (
    "History: Low back pain for 10 weeks. Completed 6 weeks of physical therapy without relief. "
    "Denies bowel or bladder changes, saddle numbness or fever. No prior imaging of the spine.\n"
    "Plan: request MRI of the lumbar spine."
)
WANTED = ["conservative_therapy_weeks", "red_flags_present", "prior_imaging_done", "symptom_duration_weeks"]


def one(fact, documents=(NOTE,), wanted=("conservative_therapy_weeks",)):
    return check([fact], list(documents), list(wanted))[0]


def test_a_fact_with_a_real_quote_is_verified():
    got = one(RawFact("conservative_therapy_weeks", "6", "Completed 6 weeks of physical therapy"))
    assert (got.status, got.value, got.document_index) == ("verified", 6, 0)


def test_quotes_match_ignoring_case_and_spacing():
    got = one(RawFact("conservative_therapy_weeks", "6", "completed   6 WEEKS of physical therapy"))
    assert got.status == "verified"


def test_as08_a_fact_whose_quote_isnt_in_the_note_is_dropped():
    got = one(RawFact("conservative_therapy_weeks", "8", "Completed 8 weeks of physical therapy"))
    assert (got.status, got.value, got.reason) == ("dropped", None, "The quote doesn't appear in any document")


def test_a_number_that_isnt_in_its_quote_is_dropped():
    got = one(RawFact("conservative_therapy_weeks", "8", "Completed 6 weeks of physical therapy"))
    assert (got.status, got.reason) == ("dropped", "The quote doesn't contain the number 8")


def test_zero_passes_when_the_quote_says_nothing_was_tried():
    note = "Has not tried physical therapy."
    assert one(RawFact("conservative_therapy_weeks", "0", "Has not tried physical therapy"), documents=[note]).value == 0
    assert number_in("six weeks of physical therapy", 6)
    assert not number_in("Completed physical therapy", 0)


@pytest.mark.parametrize("value", ["about six", "true", "-3"])
def test_invalid_values_are_dropped(value):
    assert one(RawFact("conservative_therapy_weeks", value, "Completed 6 weeks of physical therapy")).status == "dropped"


@pytest.mark.parametrize("value", [None, "unknown", "Not documented", ""])
def test_unknown_means_not_documented(value):
    assert one(RawFact("conservative_therapy_weeks", value, None)).status == "not_documented"


def test_a_fact_without_a_quote_is_dropped():
    assert one(RawFact("red_flags_present", "false", None), wanted=("red_flags_present",)).reason == "No supporting quote"


def test_every_wanted_field_gets_one_answer_and_extras_are_ignored():
    facts = [
        RawFact("made_up_field", "1", "Completed 6 weeks"),
        RawFact("red_flags_present", "false", "Denies bowel or bladder changes"),
        RawFact("red_flags_present", "true", "Denies bowel or bladder changes"),  # second answer ignored
    ]
    checked = check(facts, [NOTE], WANTED)
    assert [c.field for c in checked] == WANTED
    assert checked[1].value is False
    assert [c.status for c in checked] == ["not_documented", "verified", "not_documented", "not_documented"]


def test_the_rules_baseline_reads_a_plain_note():
    raw, usage = BaselineExtractor().extract("72148", [NOTE], WANTED)
    checked = {c.field: c.value for c in check(raw, [NOTE], WANTED)}
    assert checked == {"conservative_therapy_weeks": 6, "red_flags_present": False, "prior_imaging_done": False,
                       "symptom_duration_weeks": 10}
    assert usage["cost_usd"] == 0.0


def test_the_rules_baseline_is_fooled_by_a_negation_next_to_a_red_flag():
    note = "No fever, but reports new saddle numbness since Tuesday."
    raw, _ = BaselineExtractor().extract("72148", [note], ["red_flags_present"])
    assert check(raw, [note], ["red_flags_present"])[0].value is False  # wrong, and the test set knows it


def test_the_scorer_counts_false_fills():
    class Hallucinates:
        model = "always-yes"

        def extract(self, service_code, documents, wanted):
            first_sentence = documents[0].split("\n")[0]
            return [RawFact(f, "true", first_sentence) for f in wanted if f.endswith(("_present", "_done", "_apneas"))], {}

    eval_run.make_extractor = lambda name, model: Hallucinates()
    try:
        result = eval_run.score("fake", limit=10)
    finally:
        import importlib

        importlib.reload(eval_run)
    assert result["false_fills"] > 0
    assert result["correct"] < result["slots"]


def test_the_rules_baseline_score_doesnt_regress():
    result = eval_run.score("rules")
    assert result["cases"] == 40 and result["failures"] == 0
    assert result["accuracy"] >= 0.75
