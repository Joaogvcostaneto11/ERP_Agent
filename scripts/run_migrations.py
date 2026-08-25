"""Apply SQL migration files to one of the configured databases.

    python scripts/run_migrations.py db/migrations/002_bills_audit.sql ...
    python scripts/run_migrations.py --url-var DEVCARE_WRITE_DATABASE_URL ...

Why this exists rather than `sqlcmd -i`: `GO` is a sqlcmd/SSMS batch separator,
not T-SQL, so handing a migration file straight to pyodbc fails on it. This
splits on GO the way sqlcmd would, then runs each batch.

Every migration in db/migrations/ is written to be safely re-runnable
(`IF OBJECT_ID(...) IS NULL`), so applying one twice is not an error.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

_REPO_ROOT = Path(__file__).resolve().parents[1]

# A line containing only GO (any case, optional whitespace) separates batches.
_GO = re.compile(r"(?im)^[ \t]*GO[ \t]*$")


def batches(sql: str) -> list[str]:
    return [b for b in _GO.split(sql) if b.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path, help="migration .sql files, in order")
    ap.add_argument("--url-var", default="BILLS_WRITE_DATABASE_URL",
                    help="env var holding the SQLAlchemy URL (default: %(default)s)")
    args = ap.parse_args()

    load_dotenv(_REPO_ROOT / ".env")
    url = os.environ.get(args.url_var)
    if not url:
        print(f"{args.url_var} is not set", file=sys.stderr)
        return 2

    missing = [f for f in args.files if not f.is_file()]
    if missing:
        print(f"no such file: {', '.join(str(f) for f in missing)}", file=sys.stderr)
        return 2

    # Never print the URL itself; it carries the password.
    database = url.rsplit("/", 1)[-1].split("?")[0]
    print(f"target database: {database} (via {args.url_var})")

    engine = create_engine(url)
    for path in args.files:
        parts = batches(path.read_text(encoding="utf-8"))
        try:
            # One transaction per file: a migration that fails part way leaves
            # nothing behind to reconcile by hand.
            with engine.begin() as conn:
                for batch in parts:
                    conn.execute(text(batch))
        except Exception as e:
            print(f"FAILED  {path}: {e}", file=sys.stderr)
            return 1
        print(f"applied {path}  ({len(parts)} batch{'es' if len(parts) != 1 else ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
