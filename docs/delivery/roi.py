"""ROI calculator for the pilot, with every assumption in one place.

    python docs/delivery/roi.py              # the three scenarios
    python docs/delivery/roi.py --self-test

EVERY INPUT BELOW IS A HYPOTHESIS for the fictional Tallowmere Health Plan, to be replaced
with the client's numbers in discovery. Nothing here is a measured saving. The one input
that decides the case (minutes of nurse time saved per case) depends on extraction accuracy,
which hasn't been measured for Claude yet; the scenarios show what happens at each level.
"""
from __future__ import annotations

import argparse

# Volumes (hypothesis, from the discovery pack)
REQUESTS_PER_WEEK = 1000
SHARE_FAXED_OR_PHONED = 0.50          # re-keyed by hand today
SHARE_NEEDING_REVIEW = 0.80           # the rest close at intake (no auth needed, ineligible)
WEEKS_PER_YEAR = 50

# Team (hypothesis, from the discovery pack): today's workload has to fit in these hours.
COORDINATORS = 6
NURSES = 14
HOURS_PER_PERSON_YEAR = 1800

# People costs, fully loaded per hour (hypothesis, US health plan)
COORDINATOR_PER_HOUR = 32.0
NURSE_PER_HOUR = 60.0

# Today (hypothesis)
REKEY_MINUTES = 9.0
RFI_SHARE_TODAY = 0.40
RFI_ROUNDS_TODAY = 1.8                # documents asked for one at a time
COORDINATOR_MINUTES_PER_RFI_ROUND = 12.0
NURSE_MINUTES_FINDING_FACTS = 15.0

# With the system (hypothesis)
REKEY_MINUTES_AFTER = 1.0             # check the connector's record instead of typing
RFI_SHARE_AFTER = 0.30                # everything missing asked for at once
RFI_ROUNDS_AFTER = 1.1
AI_COST_PER_CASE = 0.04               # Claude Opus 5.5 estimate from published prices; not measured yet

# Costs
BUILD_COST = 180_000.0                # pilot build and rollout (engineering, integration, training)
RUN_COST_PER_YEAR = 60_000.0          # hosting, support, model governance

# What nobody knows yet: nurse minutes saved per case depends on extraction accuracy.
SCENARIOS = {
    "low (rules-level accuracy: reviewers re-check everything)": 2.0,
    "expected (most facts right, quotes speed up checking)": 6.0,
    "high (facts rarely corrected)": 9.0,
}


def yearly(nurse_minutes_saved: float) -> dict:
    requests = REQUESTS_PER_WEEK * WEEKS_PER_YEAR
    reviewed = requests * SHARE_NEEDING_REVIEW
    rekey_hours = requests * SHARE_FAXED_OR_PHONED * (REKEY_MINUTES - REKEY_MINUTES_AFTER) / 60
    rfi_hours = reviewed * (RFI_SHARE_TODAY * RFI_ROUNDS_TODAY - RFI_SHARE_AFTER * RFI_ROUNDS_AFTER) \
        * COORDINATOR_MINUTES_PER_RFI_ROUND / 60
    nurse_hours = reviewed * nurse_minutes_saved / 60
    savings = (rekey_hours + rfi_hours) * COORDINATOR_PER_HOUR + nurse_hours * NURSE_PER_HOUR
    ai_cost = reviewed * AI_COST_PER_CASE
    net = savings - RUN_COST_PER_YEAR - ai_cost
    return {
        "coordinator_hours_saved": round(rekey_hours + rfi_hours),
        "nurse_hours_saved": round(nurse_hours),
        "gross_savings": round(savings),
        "ai_cost": round(ai_cost),
        "net_per_year": round(net),
        "payback_months": round(12 * BUILD_COST / net, 1) if net > 0 else None,
    }


def capacity() -> dict:
    """Today's workload against the team's hours. Hypotheses that don't fit the headcount are wrong."""
    requests = REQUESTS_PER_WEEK * WEEKS_PER_YEAR
    reviewed = requests * SHARE_NEEDING_REVIEW
    coordinator_hours = (requests * SHARE_FAXED_OR_PHONED * REKEY_MINUTES
                         + reviewed * RFI_SHARE_TODAY * RFI_ROUNDS_TODAY * COORDINATOR_MINUTES_PER_RFI_ROUND) / 60
    nurse_hours = reviewed * NURSE_MINUTES_FINDING_FACTS / 60
    return {
        "coordinator_share": round(coordinator_hours / (COORDINATORS * HOURS_PER_PERSON_YEAR), 2),
        "nurse_share": round(nurse_hours / (NURSES * HOURS_PER_PERSON_YEAR), 2),
    }


def self_test() -> None:
    zero = yearly(0)
    assert zero["nurse_hours_saved"] == 0
    assert yearly(6)["net_per_year"] > zero["net_per_year"]
    # Coordinator savings alone: requests x 50% x 8 min / 60, plus the RFI rounds avoided.
    expected_rekey = 1000 * 50 * 0.5 * 8 / 60
    assert abs(zero["coordinator_hours_saved"] - round(expected_rekey + 1000 * 50 * 0.8 * (0.72 - 0.33) * 12 / 60)) <= 1
    # The hypotheses must fit the team: re-keying and chasing documents can't need more hours than exist.
    load = capacity()
    assert load["coordinator_share"] < 1.0 and load["nurse_share"] < 1.0, load
    print("self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    print("All inputs are hypotheses for a fictional plan. See the top of this file.\n")
    load = capacity()
    print(f"Sanity check: today's re-keying and document chasing take {load['coordinator_share']:.0%} of the "
          f"coordinators' hours; finding facts takes {load['nurse_share']:.0%} of the nurses' hours.\n")
    print(f"| Scenario | Nurse min saved / case | Coordinator h / yr | Nurse h / yr | Net / yr | Payback |")
    print("|---|---|---|---|---|---|")
    for name, minutes in SCENARIOS.items():
        r = yearly(minutes)
        payback = f"{r['payback_months']} months" if r["payback_months"] else "doesn't pay back"
        print(f"| {name} | {minutes:g} | {r['coordinator_hours_saved']:,} | {r['nurse_hours_saved']:,} | "
              f"${r['net_per_year']:,} | {payback} |")


if __name__ == "__main__":
    main()
