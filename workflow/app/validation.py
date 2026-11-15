"""Checks a request must pass before anyone spends time on it.

Each check returns problems a person can act on, not just "invalid".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# CPT: five digits, or four digits plus F (category II) or T (category III).
# HCPCS level II: a letter A-V followed by four digits.
SERVICE_CODE = re.compile(r"^(\d{5}|\d{4}[FT]|[A-V]\d{4})$")

# ICD-10-CM: a letter (U is reserved), a digit, a digit or letter, then optionally
# a dot and one to four more characters. Accepted with or without the dot.
DIAGNOSIS_CODE = re.compile(r"^[A-TV-Z]\d[0-9A-Z](\.?[0-9A-Z]{1,4})?$")

# Synthetic member IDs only, so a real ID can't slip into a demo by accident.
SYNTHETIC_MEMBER = re.compile(r"^SYN-M\d{4,}$")


@dataclass(frozen=True)
class Problem:
    field: str
    code: str
    message: str


def npi_check_digit(first_nine: str) -> int:
    """The NPI check digit: Luhn over the nine digits, with the 80840 prefix's fixed 24 added."""
    total = 24
    for position, char in enumerate(reversed(first_nine)):
        digit = int(char)
        if position % 2 == 0:  # double every other digit, starting from the rightmost
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return (10 - total % 10) % 10


def npi_is_valid(npi: str) -> bool:
    return len(npi) == 10 and npi.isdigit() and npi_check_digit(npi[:9]) == int(npi[9])


def check_request(
    *,
    member_id: str,
    provider_npi: str,
    service_code: str,
    diagnosis_codes: list[str],
    service_date_start: date,
    service_date_end: date | None,
) -> list[Problem]:
    """Format checks that need nothing but the request itself."""
    problems: list[Problem] = []
    if not SYNTHETIC_MEMBER.match(member_id):
        problems.append(Problem("member_id", "member_id_format", "Member ID must be a synthetic ID like SYN-M0001"))
    if not provider_npi.isdigit() or len(provider_npi) != 10:
        problems.append(Problem("provider_npi", "npi_format", "Provider NPI must be exactly 10 digits"))
    elif not npi_is_valid(provider_npi):
        problems.append(Problem("provider_npi", "npi_check_digit", "Provider NPI check digit is invalid"))
    if not SERVICE_CODE.match(service_code):
        problems.append(Problem("service_code", "service_code_format", f"Service code {service_code!r} isn't a CPT or HCPCS code"))
    if not diagnosis_codes:
        problems.append(Problem("diagnosis_codes", "diagnosis_missing", "At least one diagnosis code is needed"))
    for code in diagnosis_codes:
        if not DIAGNOSIS_CODE.match(code):
            problems.append(Problem("diagnosis_codes", "diagnosis_format", f"Diagnosis code {code!r} isn't an ICD-10-CM code"))
    if service_date_end is not None and service_date_end < service_date_start:
        problems.append(Problem("service_date_end", "date_order", "Service end date is before the start date"))
    return problems


@dataclass(frozen=True)
class CoveragePeriod:
    start: date
    end: date | None  # None: still covered


def covered_on(periods: list[CoveragePeriod], day: date) -> bool:
    """Whether any coverage period includes the day (both ends inclusive)."""
    return any(p.start <= day and (p.end is None or day <= p.end) for p in periods)
