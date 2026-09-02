"""Enforce the vulnerability-scan exception policy (E23-07).

`deploy/security/scan-exceptions.toml` is the single, reviewed list of advisories
the scanners are allowed to skip. Every entry must carry a `reason` and a future
`expires` date (≤ 90 days out). This script is the CI gate and also emits the
scanner flags from the same file, so the exception list can never drift from what
actually runs.

    python tools/security/check_scan_exceptions.py --check          # gate (exit 1 on a problem)
    python tools/security/check_scan_exceptions.py --pip-audit-args  # "--ignore-vuln A ..."
    python tools/security/check_scan_exceptions.py --trivyignore     # .trivyignore on stdout
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT = _ROOT / "deploy" / "security" / "scan-exceptions.toml"
_MAX_WINDOW_DAYS = 90


@dataclass(frozen=True)
class Exception_:
    scanner: str
    id: str
    expires: str
    reason: str


@dataclass
class Exceptions:
    pip_audit: list[Exception_] = field(default_factory=list)
    trivy: list[Exception_] = field(default_factory=list)

    def all(self) -> list[Exception_]:
        return [*self.pip_audit, *self.trivy]


def load(path: Path = _DEFAULT) -> Exceptions:
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    out = Exceptions()
    for key, bucket in (("pip_audit", out.pip_audit), ("trivy", out.trivy)):
        for raw in data.get(key, []):
            bucket.append(
                Exception_(
                    scanner=key,
                    id=str(raw.get("id", "")).strip(),
                    expires=str(raw.get("expires", "")).strip(),
                    reason=str(raw.get("reason", "")).strip(),
                )
            )
    return out


def validate(exceptions: Exceptions, *, today: _dt.date | None = None) -> list[str]:
    today = today or _dt.date.today()
    problems: list[str] = []
    for exc in exceptions.all():
        where = f"[{exc.scanner}] {exc.id or '<no id>'}"
        if not exc.id:
            problems.append(f"{where}: missing `id`")
        if not exc.reason:
            problems.append(f"{where}: missing `reason`")
        try:
            expires = _dt.date.fromisoformat(exc.expires)
        except ValueError:
            problems.append(f"{where}: `expires` must be ISO YYYY-MM-DD, got {exc.expires!r}")
            continue
        if expires < today:
            problems.append(
                f"{where}: expired {expires} — renew with fresh justification or remove"
            )
        elif (expires - today).days > _MAX_WINDOW_DAYS:
            problems.append(
                f"{where}: `expires` {expires} is more than {_MAX_WINDOW_DAYS} days out — "
                "an exception is a stopgap"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=_DEFAULT)
    parser.add_argument("--check", action="store_true", help="validate; exit 1 on any problem")
    parser.add_argument("--pip-audit-args", action="store_true", help="print --ignore-vuln flags")
    parser.add_argument("--trivyignore", action="store_true", help="print .trivyignore lines")
    args = parser.parse_args(argv)

    exceptions = load(args.path)

    if args.pip_audit_args:
        print(" ".join(f"--ignore-vuln {e.id}" for e in exceptions.pip_audit))
        return 0
    if args.trivyignore:
        for e in exceptions.trivy:
            print(f"# {e.reason} (expires {e.expires})")
            print(e.id)
        return 0

    problems = validate(exceptions)
    if problems:
        print("scan-exception policy violations:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"scan exceptions OK ({len(exceptions.all())} active)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
