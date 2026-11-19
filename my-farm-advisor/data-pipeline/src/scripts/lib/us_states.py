"""US state FIPS to abbreviation/name lookup shared by pipeline helpers.

Kept in one place so farm metadata, dashboards, and report renderers agree on the
same state table instead of carrying private copies.
"""

from __future__ import annotations

STATE_FIPS: dict[str, tuple[str, str]] = {
    "01": ("AL", "Alabama"),
    "02": ("AK", "Alaska"),
    "04": ("AZ", "Arizona"),
    "05": ("AR", "Arkansas"),
    "06": ("CA", "California"),
    "08": ("CO", "Colorado"),
    "09": ("CT", "Connecticut"),
    "10": ("DE", "Delaware"),
    "11": ("DC", "District of Columbia"),
    "12": ("FL", "Florida"),
    "13": ("GA", "Georgia"),
    "15": ("HI", "Hawaii"),
    "16": ("ID", "Idaho"),
    "17": ("IL", "Illinois"),
    "18": ("IN", "Indiana"),
    "19": ("IA", "Iowa"),
    "20": ("KS", "Kansas"),
    "21": ("KY", "Kentucky"),
    "22": ("LA", "Louisiana"),
    "23": ("ME", "Maine"),
    "24": ("MD", "Maryland"),
    "25": ("MA", "Massachusetts"),
    "26": ("MI", "Michigan"),
    "27": ("MN", "Minnesota"),
    "28": ("MS", "Mississippi"),
    "29": ("MO", "Missouri"),
    "30": ("MT", "Montana"),
    "31": ("NE", "Nebraska"),
    "32": ("NV", "Nevada"),
    "33": ("NH", "New Hampshire"),
    "34": ("NJ", "New Jersey"),
    "35": ("NM", "New Mexico"),
    "36": ("NY", "New York"),
    "37": ("NC", "North Carolina"),
    "38": ("ND", "North Dakota"),
    "39": ("OH", "Ohio"),
    "40": ("OK", "Oklahoma"),
    "41": ("OR", "Oregon"),
    "42": ("PA", "Pennsylvania"),
    "44": ("RI", "Rhode Island"),
    "45": ("SC", "South Carolina"),
    "46": ("SD", "South Dakota"),
    "47": ("TN", "Tennessee"),
    "48": ("TX", "Texas"),
    "49": ("UT", "Utah"),
    "50": ("VT", "Vermont"),
    "51": ("VA", "Virginia"),
    "53": ("WA", "Washington"),
    "54": ("WV", "West Virginia"),
    "55": ("WI", "Wisconsin"),
    "56": ("WY", "Wyoming"),
}


def state_abbr(fips: str | None) -> str | None:
    """Return the two-letter abbreviation for a state FIPS code."""
    if not fips:
        return None
    record = STATE_FIPS.get(str(fips).zfill(2))
    return record[0] if record else None


def state_name(fips: str | None) -> str | None:
    """Return the full state name for a state FIPS code."""
    if not fips:
        return None
    record = STATE_FIPS.get(str(fips).zfill(2))
    return record[1] if record else None


_ABBREVIATIONS = {abbr for abbr, _ in STATE_FIPS.values()}
_NAMES = {name.upper(): abbr for abbr, name in STATE_FIPS.values()}


def normalize_state(value: str | None) -> str | None:
    """Normalize an explicit state value (FIPS, abbreviation, or name).

    Unrecognized values are returned uppercased rather than dropped, so an
    explicit non-US region is still honored.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        return state_abbr(raw) or raw
    upper = raw.upper()
    if upper in _ABBREVIATIONS:
        return upper
    return _NAMES.get(upper, upper)
