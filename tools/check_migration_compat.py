#!/usr/bin/env python
"""Can the *previous* app version still read every column it maps? (E06-10)

Run under the OLD app's environment against a database already migrated to the
NEW ``alembic head``. For every table the old ORM knows, issue
``SELECT <all mapped columns> FROM <table> WHERE false``. A column that a
migration dropped or renamed — but the old code still SELECTs — makes PostgreSQL
error, and this script exits non-zero. That is exactly the failure a rolling
update must never hit (docs/CONVENTIONS.md, expand/contract).
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, select, text

from bbz_core.infra.models import Base
from bbz_core.settings import get_settings


def main() -> int:
    engine = create_engine(get_settings().database_url_sync)
    failures: list[str] = []
    with engine.connect() as conn:
        for name, table in sorted(Base.metadata.tables.items()):
            try:
                conn.execute(select(*table.c).where(text("false")))
            except Exception as exc:
                first_line = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
                failures.append(f"{name}: {first_line}")
    engine.dispose()

    if failures:
        print("FAIL — the previous app version would break on the new schema:")
        for f in failures:
            print(f"  - {f}")
        print("\nSplit the change into expand/contract (docs/CONVENTIONS.md).")
        return 1
    print(f"ok — {len(Base.metadata.tables)} tables readable by the previous app version")
    return 0


if __name__ == "__main__":
    sys.exit(main())
