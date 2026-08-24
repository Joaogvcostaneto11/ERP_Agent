from __future__ import annotations
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import text

from dotenv import load_dotenv

from db.connection import get_session as _read_session
from db.bills_connection import get_bills_write_session
from logic.chat.audit import AuditLog
from logic.bills.audit_writer import BillAuditWriter
from logic.bills.extract.ocr import pdf_to_text
from logic.bills.pending import PendingProposalStore
from logic.bills.rules.loader import RuleLoader
from logic.bills.rules.proposal import RuleChangeProposal, apply as apply_patch, validate
from logic.bills.rules.proposer import RuleDraftError, RuleProposer
from logic.bills.rules.schema_probe import SchemaProbe, SchemaUnavailable
from logic.bills.rules.store import RuleStore
from logic.bills.service import BillService
from logic.bills.write_executor import BillWriteExecutor
from logic.common.password_gate import install_password_gate

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")

_RULES_DIR = _REPO_ROOT / "business_rules" / "bills"
_WRITE_LOG_PATH = Path(os.environ.get(
    "BILLS_WRITE_LOG_PATH", str(_REPO_ROOT / "logs" / "bills_writes.jsonl")))
_UI_DIR = _REPO_ROOT / "ui" / "bills"
_OPERATOR_COOKIE = "bills_operator"
# Writes land in whatever database BILLS_WRITE_DATABASE_URL points at (DevDB).
# Deliberately not a second, independent statement of the target: when the
# prefix named a database of its own, it drifted from the connection and the
# audit table was created somewhere the inserts never looked.
_TABLE_PREFIX = os.environ.get("BILLS_TABLE_PREFIX", "dbo.")

app = FastAPI(title="Bill Ingestion")

# This service writes to the ERP database, so it is gated whenever
# BILLS_APP_PASSWORD is set. Unset (local dev) installs no gate at all. The
# secret is deliberately separate from the chat service's APP_PASSWORD: leaking
# the read-only service must not hand over the one that writes.
install_password_gate(app, os.environ.get("BILLS_APP_PASSWORD"),
                      realm="Bill Ingestion")


@app.exception_handler(SchemaUnavailable)
async def _schema_unavailable(_request: Request, exc: SchemaUnavailable) -> Response:
    return JSONResponse({"detail": str(exc)}, status_code=503)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    """Render's health check. Declared here, above the StaticFiles mount at "/",
    because that mount answers anything not already routed — and exempt from the
    gate, or the check gets a 401 and the service never goes live."""
    return {"status": "ok"}

_service: BillService | None = None
_pending = PendingProposalStore()


def _read(sql: str, params: dict) -> list[dict]:
    with _read_session() as s:
        result = s.execute(text(sql), params or {})
        cols = list(result.keys())
        return [dict(zip(cols, row)) for row in result.fetchall()]


def _build_anthropic():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def get_service() -> BillService:
    global _service
    if _service is None:
        rule = RuleLoader(_RULES_DIR).rule()
        _service = BillService(
            anthropic_client=_build_anthropic(), ocr_fn=pdf_to_text, rule=rule,
            reader=_read, pending=_pending,
            executor=BillWriteExecutor(get_bills_write_session, table_prefix=_TABLE_PREFIX),
            audit=BillAuditWriter(AuditLog(_WRITE_LOG_PATH),
                                  session_factory=get_bills_write_session,
                                  table_prefix=_TABLE_PREFIX),
            model="claude-sonnet-4-6", table_prefix=_TABLE_PREFIX)
    return _service


def reset_service() -> None:
    """Drop the memoised service so the next request rebuilds it from the rule
    document on disk. RuleLoader parses that document once in __init__, so an
    applied rule change is invisible until this runs."""
    global _service, _schema_probe
    _service = None
    _schema_probe = None


_schema_probe: SchemaProbe | None = None


def get_schema_probe() -> SchemaProbe:
    global _schema_probe
    if _schema_probe is None:
        _schema_probe = SchemaProbe(_read)
    return _schema_probe


def get_rule_store() -> RuleStore:
    return RuleStore(_RULES_DIR)


def get_proposer() -> RuleProposer:
    return RuleProposer(_build_anthropic(), "claude-sonnet-4-6")


def _admin_token() -> str | None:
    return os.environ.get("BILLS_ADMIN_TOKEN") or None


def _require_admin(request: Request) -> None:
    token = _admin_token()
    if not token:
        raise HTTPException(status_code=404, detail="admin rules disabled")
    try:
        ok = secrets.compare_digest(request.headers.get("X-Admin-Token", ""), token)
    except TypeError:
        # compare_digest on str rejects non-ASCII outright. A typo'd paste is a
        # wrong token, not a server fault.
        ok = False
    if not ok:
        raise HTTPException(status_code=403, detail="invalid admin token")


def _rule_audit() -> AuditLog:
    return AuditLog(_WRITE_LOG_PATH)


def _operator(request: Request) -> str | None:
    return request.cookies.get(_OPERATOR_COOKIE)


@app.post("/bills/operator")
def set_operator(response: Response, body: dict) -> dict:
    name = (body or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    response.set_cookie(_OPERATOR_COOKIE, name, httponly=True, samesite="lax",
                        max_age=60 * 60 * 24 * 7)
    return {"operator": name}


@app.post("/bills/upload")
async def upload(request: Request, file: UploadFile = File(...)) -> Response:
    if not _operator(request):
        return JSONResponse({"detail": "operator not set"}, status_code=400)
    data = await file.read()
    try:
        proposal = get_service().upload(data)
    except RuntimeError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    return JSONResponse(proposal.model_dump(mode="json"))


@app.post("/bills/stage/{proposal_id}")
async def stage(proposal_id: str, request: Request) -> Response:
    if not _operator(request):
        return JSONResponse({"detail": "operator not set"}, status_code=400)
    edited = await request.json()
    try:
        return JSONResponse(get_service().stage(proposal_id, edited))
    except RuntimeError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)


@app.post("/bills/commit/{proposal_id}")
def commit(proposal_id: str, request: Request) -> Response:
    operator = _operator(request)
    if not operator:
        return JSONResponse({"detail": "operator not set"}, status_code=400)
    try:
        return JSONResponse(get_service().commit(proposal_id, operator))
    except RuntimeError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)


@app.get("/admin/rules/enabled")
def admin_rules_enabled() -> dict:
    return {"enabled": _admin_token() is not None}


@app.get("/admin/rules/current")
def admin_rules_current(request: Request) -> dict:
    _require_admin(request)
    store = get_rule_store()
    rule = store.current()
    probe = get_schema_probe()
    tables = [rule.header.table, rule.lines.table,
              rule.matching.supplier.table, rule.matching.article.table]
    return {
        "version": rule.version,
        "rule": rule.model_dump(mode="json"),
        "schema": {t: sorted(c.name for c in probe.columns(t).values()) for t in tables},
        "history": store.versions(),
    }


@app.post("/admin/rules/draft")
async def admin_rules_draft(request: Request) -> Response:
    _require_admin(request)
    prose = (await request.json()).get("prose", "").strip()
    if not prose:
        return JSONResponse({"detail": "prose required"}, status_code=400)
    rule = get_rule_store().current()
    probe = get_schema_probe()
    try:
        proposal = get_proposer().draft(prose, rule, probe)
    except RuleDraftError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    # base_version is whatever the model wrote; the 409 check in /apply is only
    # meaningful against the version actually on disk, so stamp it here.
    proposal.base_version = rule.version
    return JSONResponse({
        "proposal": proposal.model_dump(mode="json"),
        "violations": [v.model_dump() for v in validate(proposal, rule, probe)],
    })


@app.post("/admin/rules/apply")
async def admin_rules_apply(request: Request) -> Response:
    _require_admin(request)
    body = await request.json()
    store = get_rule_store()
    rule = store.current()

    if body.get("base_version") != rule.version:
        return JSONResponse(
            {"detail": f"rule is at version {rule.version}; re-draft your change"},
            status_code=409)

    try:
        proposal = RuleChangeProposal.model_validate(body.get("proposal") or {})
    except ValidationError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)

    probe = get_schema_probe()
    violations = validate(proposal, rule, probe)
    if violations:
        return JSONResponse({"violations": [v.model_dump() for v in violations]},
                            status_code=422)

    try:
        merged = apply_patch(proposal, rule, probe)
    except ValidationError as e:
        # The merge produced a document PurchaseInvoiceRule rejects — extra="forbid"
        # catching something structural the per-change checks did not model.
        # The YAML on disk is untouched; save() has not been reached.
        return JSONResponse({"detail": f"merged rule is invalid: {e}"},
                            status_code=422)

    store.save(merged)
    _rule_audit().append({
        "ts": AuditLog.now_iso(), "kind": "rule_change", "action": "apply",
        "from_version": rule.version, "to_version": merged.version,
        # The admin's own words are the audit record; `rationale` is Claude's
        # paraphrase and cannot stand in for them. Older clients that send no
        # prose record an empty string rather than failing the apply.
        "prose": str(body.get("prose") or "").strip(),
        "rationale": proposal.rationale,
        "changes": [c.model_dump() for c in proposal.changes],
        "operator": _operator(request),
    })
    reset_service()
    return JSONResponse({"version": merged.version})


@app.post("/admin/rules/revert/{version}")
def admin_rules_revert(version: int, request: Request) -> Response:
    _require_admin(request)
    store = get_rule_store()
    previous = store.current().version
    try:
        reverted = store.revert(version)
    except FileNotFoundError:
        return JSONResponse({"detail": f"no archived rule for version {version}"},
                            status_code=404)
    _rule_audit().append({
        "ts": AuditLog.now_iso(), "kind": "rule_change", "action": "revert",
        "from_version": previous, "to_version": reverted.version,
        "reverted_to": version, "operator": _operator(request),
    })
    reset_service()
    return JSONResponse({"version": reverted.version})


@app.get("/favicon.ico", include_in_schema=False)
def _favicon() -> Response:
    return Response(status_code=204)


if _UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
