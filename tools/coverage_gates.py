"""Per-layer coverage gates (roadmap E01-07, ADR-0008).

ADR-0008: the global floor is 70 % during the foundation phase; it rises to
**≥ 90 %** on the domain, authorization, rule-DSL and workflow-engine layers as
each becomes feature-complete in Phase 1. `--cov-fail-under` is global only, so
this script reads `coverage.json` (written by `pytest --cov-report=json`) and
checks each layer against its own floor.

A gate is either **enforced** (below floor ⇒ this script exits 1 ⇒ CI fails) or
**report-only** (printed, never fails). The owning Phase-1 issue flips its gate
to enforced once the package is real and covered — the number can only ratchet
up. Run from the repo root:

    pytest --cov --cov-report=json
    python tools/coverage_gates.py            # report + fail on an enforced breach
    python tools/coverage_gates.py --strict   # fail on ANY breach (local check)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT = _ROOT / "coverage.json"


@dataclass(frozen=True)
class Gate:
    label: str
    # matched against each source file's path (normalised, forward slashes)
    contains: str
    floor: float
    enforced: bool
    owner: str  # who flips `enforced` to True


# ADR-0008 §"coverage gate". Keep `enforced=False` until the owning issue has
# the package feature-complete; then set it True in that PR.
GATES: tuple[Gate, ...] = (
    Gate("domain", "/bbz_core/domain/", 90.0, False, "Epics 03 / 05"),
    Gate("authorization", "/bbz_core/authorization/", 90.0, False, "Epic 02"),
    Gate("rule DSL", "/bbz_rule_dsl/", 90.0, False, "rule DSL (ADR-0010)"),
    Gate("workflow engine", "/bbz_core/workflow_engine/", 90.0, False, "Epic 05"),
)


@dataclass
class Measured:
    gate: Gate
    covered: int
    statements: int

    @property
    def pct(self) -> float:
        return 100.0 * self.covered / self.statements if self.statements else 100.0

    @property
    def ok(self) -> bool:
        return self.pct + 1e-9 >= self.gate.floor


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    return p if p.startswith("/") else "/" + p


def measure(report: dict[str, Any], gates: tuple[Gate, ...] = GATES) -> list[Measured]:
    out = [Measured(g, 0, 0) for g in gates]
    for raw_path, entry in report.get("files", {}).items():
        path = _norm(raw_path)
        summary = entry.get("summary", {})
        for m in out:
            if m.gate.contains in path:
                m.covered += int(summary.get("covered_lines", 0))
                m.statements += int(summary.get("num_statements", 0))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=_DEFAULT)
    parser.add_argument(
        "--strict", action="store_true", help="fail on any breach, not just enforced gates"
    )
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"no coverage report at {args.path} — run `pytest --cov-report=json` first")
        return 1

    report = json.loads(args.path.read_text(encoding="utf-8"))
    rows = measure(report)

    width = max(len(m.gate.label) for m in rows)
    print(f"{'layer'.ljust(width)}   cover   floor  mode         status")
    failures: list[str] = []
    for m in rows:
        mode = "enforced" if m.gate.enforced else "report-only"
        if m.statements == 0:
            status = "no code yet"
        elif m.ok:
            status = "ok"
        else:
            status = f"BELOW by {m.gate.floor - m.pct:.1f}pt"
            if m.gate.enforced or args.strict:
                failures.append(
                    f"{m.gate.label}: {m.pct:.1f}% < {m.gate.floor:.0f}% — raise coverage, "
                    f"or keep the gate report-only until the package is ready ({m.gate.owner})"
                )
        print(
            f"{m.gate.label.ljust(width)}  {m.pct:5.1f}%  {m.gate.floor:5.0f}%  "
            f"{mode.ljust(11)}  {status}"
        )

    total = report.get("totals", {}).get("percent_covered")
    if total is not None:
        print(f"\nglobal: {total:.1f}% (floor 70% — enforced by --cov-fail-under)")

    if failures:
        print("\ncoverage gate failures:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
