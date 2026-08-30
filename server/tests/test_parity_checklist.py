"""docs/mockup-parity-checklist.md is well-formed and covers FEATURES.md (E07-01).

A "doc-link-check": every issue reference is a plausible number, the
``E07-xx ↔ #issue`` map is consistent, every row has a valid status, and every
``.ai/FEATURES.md`` feature area is mentioned.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_DOC = _ROOT / "docs" / "mockup-parity-checklist.md"
_FEATURES = _ROOT / ".ai" / "FEATURES.md"

_STATUSES = {"todo", "backend-done", "in-progress", "done", "n/a-here"}

# E07-01 = #96 … #99 consecutive, then the deduped odd numbers
_E07_MAP = {
    1: 96,
    2: 97,
    3: 98,
    4: 99,
    5: 101,
    6: 103,
    7: 105,
    8: 107,
    9: 109,
    10: 111,
    11: 113,
    12: 115,
    13: 117,
    14: 119,
    15: 121,
    16: 123,
    17: 125,
    18: 127,
    19: 129,
}


def _text() -> str:
    return _DOC.read_text(encoding="utf-8")


def test_every_issue_reference_is_a_plausible_number() -> None:
    refs = [int(n) for n in re.findall(r"#(\d+)", _text())]
    assert refs, "no issue references found"
    assert all(1 <= n <= 1500 for n in refs), [n for n in refs if not 1 <= n <= 1500]


def test_the_e07_issue_map_is_consistent() -> None:
    # rows like: [#101](../../issues/101) (E07-05)
    for issue, ep in re.findall(r"\[#(\d+)\]\(\.\./\.\./issues/\d+\)\s*\(E07-(\d+)\)", _text()):
        want = _E07_MAP[int(ep)]
        assert want == int(issue), f"E07-{ep} should be #{want}, got #{issue}"
    # the link target matches the label
    for label, target in re.findall(r"\[#(\d+)\]\(\.\./\.\./issues/(\d+)\)", _text()):
        assert label == target, f"link #{label} points at issues/{target}"


def test_every_table_row_has_a_valid_status() -> None:
    bad: list[str] = []
    for line in _text().splitlines():
        if not line.startswith("|") or set(line) <= set("| -"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        status = cells[-1].strip("`").lower()
        if not status or status == "status":
            continue
        # the cell must START with a known status token (a trailing note is ok)
        if not any(status == v or status.startswith(v + " ") for v in _STATUSES):
            bad.append(line)
    assert not bad, bad


def test_all_features_areas_are_covered() -> None:
    doc = _text().lower()
    must_mention = [
        "work queue",
        "keypad",
        "phonebook",
        "quick-dial",
        "call categoriz",
        "priority",
        "reduced-motion",
        "resizable",
        "sidebar",
        "archive",
        "postprocessing",
        "reactivation",
        "take-over",
        "presence",
        "totp",
        "epk",
        "and / or / xor",
        "versioned workflow",
        "dwd weather",
        "monitor routing",
        "bbz-os",
        "bku agent",
        "doorbell",
        "siedle",
        "trigger rule",
        "bma",
        "coda video",
        "alarm source",
        "accessibility",
        "theme token",
        "i18n",
    ]
    missing = [m for m in must_mention if m not in doc]
    assert not missing, f"parity checklist does not mention: {missing}"


def test_it_names_its_own_enforcing_test_and_the_feature_source() -> None:
    doc = _text()
    assert "test_parity_checklist.py" in doc
    assert _FEATURES.name in doc  # FEATURES.md is cited as the baseline
    assert _FEATURES.read_text(encoding="utf-8").strip()  # and exists
