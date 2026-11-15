"""Step 2: the catalogue and the format checks. No database needed."""
from datetime import date
from pathlib import Path

import pytest

from app import catalogue
from app.validation import CoveragePeriod, check_request, covered_on, npi_check_digit, npi_is_valid


def valid_request(**overrides):
    request = dict(
        member_id="SYN-M0001",
        provider_npi="1234567893",
        service_code="72148",
        diagnosis_codes=["M54.50"],
        service_date_start=date(2026, 12, 1),
        service_date_end=None,
    )
    request.update(overrides)
    return request


# --- NPI ------------------------------------------------------------------------

def test_npi_check_digit_matches_the_published_example():
    # CMS's worked example: 123456789 has check digit 3.
    assert npi_check_digit("123456789") == 3
    assert npi_is_valid("1234567893")


@pytest.mark.parametrize("npi", ["1234567890", "123456789", "12345678931", "12345A7893", ""])
def test_bad_npis_are_rejected(npi):
    assert not npi_is_valid(npi)


def test_an_npi_with_a_wrong_check_digit_says_so():  # AS-07
    problems = check_request(**valid_request(provider_npi="1234567890"))
    assert [(p.field, p.code, p.message) for p in problems] == [
        ("provider_npi", "npi_check_digit", "Provider NPI check digit is invalid")
    ]


def test_an_npi_of_the_wrong_length_gets_a_different_message():
    problems = check_request(**valid_request(provider_npi="12345"))
    assert [p.code for p in problems] == ["npi_format"]


# --- codes ------------------------------------------------------------------------

@pytest.mark.parametrize("code", ["72148", "95810", "0001F", "0042T", "E0601"])
def test_service_code_formats_that_pass(code):
    assert check_request(**valid_request(service_code=code)) == []


@pytest.mark.parametrize("code", ["7214", "721488", "W1234", "ABCDE"])
def test_service_code_formats_that_fail(code):
    assert [p.code for p in check_request(**valid_request(service_code=code))] == ["service_code_format"]


@pytest.mark.parametrize("code", ["M54.50", "M5450", "G47.33", "M51.16", "S83.511A"])
def test_diagnosis_formats_that_pass(code):
    assert check_request(**valid_request(diagnosis_codes=[code])) == []


@pytest.mark.parametrize("code", ["U07.1", "M5", "54.50", "M54.50000"])
def test_diagnosis_formats_that_fail(code):
    assert [p.code for p in check_request(**valid_request(diagnosis_codes=[code]))] == ["diagnosis_format"]


def test_a_request_needs_a_diagnosis():
    assert [p.code for p in check_request(**valid_request(diagnosis_codes=[]))] == ["diagnosis_missing"]


def test_only_synthetic_member_ids_are_accepted():
    assert [p.code for p in check_request(**valid_request(member_id="123456789"))] == ["member_id_format"]


def test_end_date_before_start_date():
    problems = check_request(**valid_request(service_date_end=date(2026, 11, 30)))
    assert [p.code for p in problems] == ["date_order"]


def test_every_problem_is_reported_at_once():
    problems = check_request(**valid_request(provider_npi="1", service_code="x", diagnosis_codes=["bad"]))
    assert {p.field for p in problems} == {"provider_npi", "service_code", "diagnosis_codes"}


# --- coverage ---------------------------------------------------------------------

def test_coverage_includes_both_end_days():
    periods = [CoveragePeriod(date(2026, 1, 1), date(2026, 12, 31))]
    assert covered_on(periods, date(2026, 1, 1))
    assert covered_on(periods, date(2026, 12, 31))
    assert not covered_on(periods, date(2027, 1, 1))  # AS-04


def test_open_ended_coverage_and_gaps():
    periods = [CoveragePeriod(date(2025, 1, 1), date(2025, 6, 30)), CoveragePeriod(date(2026, 1, 1), None)]
    assert covered_on(periods, date(2030, 5, 5))
    assert not covered_on(periods, date(2025, 9, 1))
    assert not covered_on([], date(2026, 1, 1))


# --- catalogue --------------------------------------------------------------------

def test_the_real_catalogue_loads():
    cat = catalogue.load()
    assert cat.version == "2026.11-2"
    assert cat.needs_authorization("72148")
    assert not cat.needs_authorization("99213")  # AS-05
    assert not cat.needs_authorization("12345")  # not in the catalogue at all


def test_missing_documents_come_back_in_checklist_order():  # AS-02
    cat = catalogue.load()
    missing = cat.missing_documents("95810", set())
    assert [d.type for d in missing] == ["clinician_note", "sleep_questionnaire"]
    assert cat.missing_documents("95810", {"sleep_questionnaire", "clinician_note"}) == []
    assert [d.type for d in cat.missing_documents("72148", {"clinician_note", "something_else"})] == [
        "conservative_treatment_record"
    ]


def test_every_service_that_needs_authorization_has_a_checklist():
    cat = catalogue.load()
    for service in cat.services.values():
        if service.auth_required:
            assert service.required_documents, service.code


@pytest.mark.parametrize(
    "text, message",
    [
        ("services: {}", "string 'version'"),
        ("version: '1'\nservices:\n  '1': {name: x}", "missing 'auth_required'"),
        (
            "version: '1'\nservices:\n  '1': {name: x, auth_required: false, facts: [], required_documents: [{type: a, label: b}]}",
            "can't require documents",
        ),
        ("version: [", "Can't read the catalogue"),
    ],
)
def test_a_broken_catalogue_fails_loudly_at_startup(tmp_path: Path, text, message):
    path = tmp_path / "catalogue.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(catalogue.CatalogueError, match=message):
        catalogue.load(path)
