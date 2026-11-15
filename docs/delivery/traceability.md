# Acceptance scenarios to tests

Each acceptance scenario from [the discovery pack](../discovery/06-acceptance-scenarios.md), and the automated tests that check it. All run in CI on every push.

| Scenario | Tests |
|---|---|
| AS-01 Complete request becomes ready | `workflow/tests/test_intake.py::test_as01_complete_standard_request_becomes_ready_for_review`; browser test `web/e2e/review-flow.spec.ts` |
| AS-02 Missing documents asked for at once | `test_intake.py::test_as02_missing_documents_are_asked_for_all_at_once`, `test_some_documents_keep_the_case_pended_and_update_the_request` |
| AS-03 Expedited 72-hour clock | `test_clocks_and_audit.py::test_as03_an_expedited_request_runs_on_a_72_hour_clock` |
| AS-04 Not eligible is closed, not denied | `test_intake.py::test_as04_member_not_covered_on_the_date_is_closed_not_denied`, `test_coverage_gaps_count` |
| AS-05 No authorization needed | `test_intake.py::test_as05_service_without_authorization_is_closed_with_the_catalogue_version`; `test_rules.py::test_the_real_catalogue_loads` |
| AS-06 Same request, two channels | `test_intake.py::test_as06_same_request_from_two_channels_opens_one_case`, `test_simultaneous_duplicates_open_exactly_one_case`; CI ingest of the X12 and FHIR fixtures |
| AS-07 Invalid NPI refused with a reason | `test_rules.py::test_an_npi_with_a_wrong_check_digit_says_so`; `test_intake.py::test_as07_invalid_npi_is_rejected_with_a_usable_reason`; `connectors/test/reliability.test.ts` "AS-07: a rejected record is replayed from the fixed source" |
| AS-08 Fact without a matching quote is dropped | `test_extraction.py::test_as08_a_fact_whose_quote_isnt_in_the_note_is_dropped`; `test_extraction_flow.py::test_answers_are_checked_against_the_documents_and_the_case_goes_to_review`; browser test |
| AS-09 AI downtime doesn't stop intake | `test_extraction_flow.py::test_as09_a_failed_extraction_sends_the_case_to_manual_entry`, `test_as09_if_the_worker_never_answers_the_sweep_gives_up_after_ten_minutes`; CI AI-outage drills in compose and Kubernetes |
| AS-10 A nurse can't deny | `test_lifecycle.py::test_as10_a_nurse_cant_deny`; `test_auth.py::test_as10_a_nurse_cant_deny_over_the_api`; browser test "the server refuses a decision the page doesn't offer" |
| AS-11 Denial needs a medical director and a reason | `test_lifecycle.py::test_as11_...`; `test_auth.py::test_as11_a_medical_director_denies_with_a_reason`; `test_clocks_and_audit.py::test_the_database_refuses_a_denial_without_a_reason`; browser test |
| AS-12 Audit trail complete and uneditable | `test_clocks_and_audit.py::test_as12_the_audit_trail_is_complete_and_in_order`, `test_as12_audit_rows_cant_be_edited_or_deleted` |
| AS-13 Connector survives an upstream timeout | `connectors/test/reliability.test.ts` "AS-13: ..." (two tests) |
| AS-14 CMS metrics are correct | `test_reports.py::test_as14_cms_metrics_match_a_hand_calculation` |
