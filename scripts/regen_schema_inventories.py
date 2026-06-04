"""Regenerate the per-database "Full Table Inventory" sections and the
Databases summary counts in docs/db_schema.md from the live SQL Server.

Hand-written prose sections (Core Document Model, SYS Tables, clinic
specifics, Inferred Business Rules) and the Purpose column are preserved
verbatim. Only the mechanically-derivable parts are refreshed.

Rules reverse-engineered from the existing doc:
  * Group key = the leading run of letters in the table name (case-sensitive),
    e.g. SYS00 -> "SYS", CRM_Anexos -> "CRM", SYSLOG -> "SYSLOG".
  * Group header count = ALL base tables in the group (including empty ones).
  * Group order = table count desc, then group key asc (ASCII).
  * Body rows = only tables with rows > 0, sorted asc (ASCII) by name.

Usage:
  python scripts/regen_schema_inventories.py            # rewrite the doc
  python scripts/regen_schema_inventories.py --validate # diff DevDB only, no write
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

DOC = Path(__file__).resolve().parents[1] / "docs" / "db_schema.md"

# Inventory sections to (re)generate, in the order they appear in the doc.
# DevCare is inserted immediately after DOClinic (its schema-identical mirror).
INVENTORY_ORDER = ["DevDB", "DOClinic", "DevCare", "ForumSI"]


def _prefix(name: str) -> str:
    m = re.match(r"[A-Za-z]+", name)
    return m.group(0) if m else name


def get_inventory(conn, db: str):
    base = [r[0] for r in conn.execute(text(
        f"SELECT TABLE_NAME FROM {db}.INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_TYPE='BASE TABLE'"
    )).fetchall()]
    n_views = conn.execute(text(
        f"SELECT COUNT(*) FROM {db}.INFORMATION_SCHEMA.VIEWS"
    )).scalar()
    cols = dict(conn.execute(text(
        f"SELECT TABLE_NAME, COUNT(*) FROM {db}.INFORMATION_SCHEMA.COLUMNS "
        "GROUP BY TABLE_NAME"
    )).fetchall())
    rows = dict(conn.execute(text(
        f"SELECT t.name, SUM(p.rows) FROM {db}.sys.tables t "
        f"JOIN {db}.sys.partitions p ON t.object_id = p.object_id "
        "WHERE p.index_id IN (0, 1) GROUP BY t.name"
    )).fetchall())

    groups: dict[str, list[str]] = {}
    for t in base:
        groups.setdefault(_prefix(t), []).append(t)
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return len(base), int(n_views), ordered, rows, cols


def render_section(db: str, conn) -> list[str]:
    n_tables, n_views, ordered, rows, cols = get_inventory(conn, db)
    out = [f"## {db} — Full Table Inventory", "",
           f"Total: **{n_tables} tables**, {n_views} views", ""]
    for key, tables in ordered:
        out.append(f"### Group: {key} ({len(tables)} tables)")
        out.append("")
        out.append("| Table | Rows | Cols |")
        out.append("|---|---|---|")
        for t in sorted(tables):
            r = int(rows.get(t, 0) or 0)
            if r > 0:
                out.append(f"| {t} | {r} | {cols.get(t, 0)} |")
        out.append("")
    return out


def split_sections(lines: list[str]):
    """Split into (header_line_or_None, body_lines) blocks at '## ' headers."""
    blocks = []
    cur_header = None
    cur_body: list[str] = []
    preamble: list[str] = []
    started = False
    for ln in lines:
        if ln.startswith("## "):
            if not started:
                preamble = cur_body
                cur_body = []
                started = True
            else:
                blocks.append((cur_header, cur_body))
                cur_body = []
            cur_header = ln
        else:
            cur_body.append(ln)
    if started:
        blocks.append((cur_header, cur_body))
    return preamble, blocks


def db_counts(conn, dbs):
    out = {}
    for db in dbs:
        t = conn.execute(text(
            f"SELECT COUNT(*) FROM {db}.INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE='BASE TABLE'")).scalar()
        v = conn.execute(text(
            f"SELECT COUNT(*) FROM {db}.INFORMATION_SCHEMA.VIEWS")).scalar()
        out[db] = (int(t), int(v))
    return out


def rebuild_summary(body: list[str], counts: dict, conn) -> list[str]:
    """Update Tables/Views in the Databases summary table, add a DevCare row
    after DOClinic. Purpose text is preserved (and authored for DevCare)."""
    out = []
    for ln in body:
        m = re.match(r"\| (\w+) \| .*? \| .*? \| (.*) \|$", ln)
        if m and m.group(1) in counts:
            db = m.group(1)
            purpose = m.group(2)
            t, v = counts[db]
            out.append(f"| {db} | {t} | {v} | {purpose} |")
            if db == "DOClinic":
                t2, v2 = counts["DevCare"]
                # Match DevCare's data volume note to whether it equals DOClinic.
                dc = conn.execute(text(
                    "SELECT SUM(p.rows) FROM DevCare.sys.partitions p "
                    "WHERE p.index_id IN (0,1)")).scalar()
                do = conn.execute(text(
                    "SELECT SUM(p.rows) FROM DOClinic.sys.partitions p "
                    "WHERE p.index_id IN (0,1)")).scalar()
                note = ("Mirror of DOClinic (same schema, same data volume)"
                        if dc == do else "Mirror of DOClinic (same schema)")
                out.append(f"| DevCare | {t2} | {v2} | {note} |")
        else:
            out.append(ln)
    return out


def validate(conn):
    """Regenerate DevDB and structurally diff against the doc (group headers +
    body membership). Row/col counts are allowed to drift."""
    doc = DOC.read_text(encoding="utf-8").splitlines()
    _, blocks = split_sections(doc)
    doc_body = next(b for h, b in blocks if h.startswith("## DevDB — Full Table"))
    gen = render_section("DevDB", conn)

    def groups_of(lines):
        result = {}
        cur = None
        for ln in lines:
            mh = re.match(r"### Group: (.+) \((\d+) tables\)", ln)
            if mh:
                cur = mh.group(1)
                result[cur] = {"count": int(mh.group(2)), "tables": []}
            elif ln.startswith("| ") and not ln.startswith("| Table") and cur:
                result[cur]["tables"].append(re.match(r"\| (.+?) \|", ln).group(1))
        return result

    dg, gg = groups_of(doc_body[1:]), groups_of(gen)
    problems = 0
    for key in sorted(set(dg) | set(gg)):
        if key not in dg:
            print(f"  [gen-only group] {key}"); problems += 1; continue
        if key not in gg:
            print(f"  [doc-only group] {key}"); problems += 1; continue
        if dg[key]["count"] != gg[key]["count"]:
            print(f"  [count diff] {key}: doc={dg[key]['count']} gen={gg[key]['count']}")
            problems += 1
        if set(dg[key]["tables"]) != set(gg[key]["tables"]):
            only_doc = set(dg[key]["tables"]) - set(gg[key]["tables"])
            only_gen = set(gg[key]["tables"]) - set(dg[key]["tables"])
            print(f"  [body diff] {key}: doc-only={sorted(only_doc)} gen-only={sorted(only_gen)}")
            problems += 1
    print(f"VALIDATE DevDB: {'CLEAN' if problems == 0 else str(problems)+' problems'}")
    return problems == 0


def main():
    load_dotenv()
    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.connect() as conn:
        if "--validate" in sys.argv:
            validate(conn)
            return

        doc = DOC.read_text(encoding="utf-8").splitlines()
        preamble, blocks = split_sections(doc)
        all_dbs = ["DevDB", "DOClinic", "ForumSI", "OpenInnovation", "DevCare"]
        counts = db_counts(conn, all_dbs)

        new_lines = list(preamble)
        for header, body in blocks:
            name = header[3:].split(" — ")[0].strip()
            is_inventory = header.endswith("Full Table Inventory") and name in INVENTORY_ORDER
            if header.startswith("## Databases"):
                new_lines.append(header)
                new_lines.extend(rebuild_summary(body, counts, conn))
            elif is_inventory:
                # Replace this inventory body with a freshly generated one.
                new_lines.extend(render_section(name, conn))
                if name == "DOClinic":
                    new_lines.extend(render_section("DevCare", conn))
            else:
                new_lines.append(header)
                new_lines.extend(body)

        DOC.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print(f"Rewrote {DOC} ({len(new_lines)} lines).")


if __name__ == "__main__":
    main()
