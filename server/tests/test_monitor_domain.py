"""Monitor routing domain — the fixed catalog, the standard layout, and
assignment validation (roadmap E19-02, MASTER_PROMPT §9). Pure unit tests."""

from __future__ import annotations

import pytest

from bbz_core.domain.monitor import (
    BOTTOM_LEFT_OUTPUT_KEY,
    INPUT_KEYS,
    INPUTS,
    OUTPUT_KEYS,
    OUTPUTS,
    STANDARD_LAYOUT,
    MonitorDomainError,
    standard_layout,
    validate_assignment,
    validate_layout,
)


def test_the_catalog_matches_master_prompt_section_9() -> None:
    assert set(INPUT_KEYS) == {"bbz-os", "bku1", "bku2", "bku3", "bku4", "coda1", "coda2"}
    assert set(OUTPUT_KEYS) == {f"workplace{n}" for n in range(1, 7)} | {"large-display"}
    assert len(INPUTS) == 7 and len(OUTPUTS) == 7
    assert len({i.key for i in INPUTS}) == 7 and len({o.key for o in OUTPUTS}) == 7


def test_the_workplace_monitors_tile_the_3x2_grid() -> None:
    grid = {(o.grid_row, o.grid_col) for o in OUTPUTS if not o.is_large_display}
    assert grid == {(r, c) for r in (0, 1) for c in (0, 1, 2)}
    large = [o for o in OUTPUTS if o.is_large_display]
    assert len(large) == 1 and large[0].grid_row is None and large[0].grid_col is None


def test_bottom_left_is_the_lower_left_grid_slot() -> None:
    bl = next(o for o in OUTPUTS if o.key == BOTTOM_LEFT_OUTPUT_KEY)
    assert (bl.grid_row, bl.grid_col) == (1, 0)


def test_the_standard_layout_covers_every_output_with_a_known_input() -> None:
    assert set(STANDARD_LAYOUT) == OUTPUT_KEYS
    assert set(STANDARD_LAYOUT.values()) <= INPUT_KEYS
    # the §9 fixed rule: BBZ-OS is lower-left
    assert STANDARD_LAYOUT[BOTTOM_LEFT_OUTPUT_KEY] == "bbz-os"


def test_standard_layout_returns_an_independent_copy() -> None:
    a = standard_layout()
    a["workplace1"] = "coda2"
    assert standard_layout()["workplace1"] != "coda2"


def test_validate_layout_accepts_the_standard_layout() -> None:
    validate_layout(standard_layout())  # does not raise


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.pop("workplace1"),  # missing an output
        lambda m: m.update({"workplace9": "bku1"}),  # unknown output
        lambda m: m.update({"workplace1": "hdmi7"}),  # unknown input
    ],
)
def test_validate_layout_rejects_a_broken_mapping(mutate) -> None:  # type: ignore[no-untyped-def]
    layout = standard_layout()
    mutate(layout)
    with pytest.raises(MonitorDomainError):
        validate_layout(layout)


def test_validate_assignment_checks_both_keys() -> None:
    validate_assignment("large-display", "coda1")  # ok
    with pytest.raises(MonitorDomainError):
        validate_assignment("nope", "bbz-os")
    with pytest.raises(MonitorDomainError):
        validate_assignment("workplace1", "nope")
