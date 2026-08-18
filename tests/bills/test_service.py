from decimal import Decimal
from pathlib import Path

from logic.bills.models import Bill, BillLine
from logic.bills.pending import PendingProposalStore
from logic.bills.rules.loader import RuleLoader
from logic.bills.service import BillService

RULES_DIR = Path(__file__).resolve().parents[2] / "business_rules" / "bills"


class FakeParser:
    def __init__(self, bill):
        self._bill = bill
        self.image_calls = []
    def parse(self, pages): return self._bill
    def parse_image(self, media_type, b64):
        self.image_calls.append((media_type, b64))
        return self._bill


class FakeExecutor:
    def __init__(self): self.calls = []
    def execute(self, plan, rule):
        self.calls.append(plan)
        return {"document_chave": 99, "supplier_chave": 7, "line_chaves": [1],
                "created_supplier": False, "created_articles": []}


class FakeAudit:
    def __init__(self): self.records = []
    def record(self, **kw): self.records.append(kw)


def _reader_no_matches(sql, params):
    return []


def _reader_supplier_and_article(sql, params):
    if "Entidades" in sql and params.get("tax_id") == "500100209":
        return [{"Chave": 7, "Nome": "ACME"}]
    if "Artigos" in sql:
        return [{"Chave": 42, "Nome": "Widget"}]
    return []


def _bill():
    # 500100209 passes the PT NIF check digit (Task 10); a fixture value that
    # failed it would get blanked by upload() before matching ever ran it.
    return Bill(supplier_name="ACME", supplier_tax_id="500100209",
                number="FT1", issue_date="2026-06-01", net_total=Decimal("100"),
                vat_total=Decimal("23"), gross_total=Decimal("123"),
                lines=[BillLine(description="Widget", quantity=Decimal("2"),
                                unit_price=Decimal("50"), vat_rate=Decimal("23"),
                                total=Decimal("100"))])


def _service(reader, executor=None, monkeypatch_ocr=None):
    svc = BillService(anthropic_client=None, ocr_fn=lambda b: [],
                      rule=RuleLoader(RULES_DIR).rule(), reader=reader,
                      pending=PendingProposalStore(), executor=executor or FakeExecutor(),
                      audit=FakeAudit(), model="claude-sonnet-4-6")
    svc._parser = FakeParser(_bill())  # inject parser (constructor builds a real one)
    return svc


def test_upload_produces_matched_proposal():
    svc = _service(_reader_supplier_and_article)
    proposal = svc.upload(b"%PDF")
    assert proposal.supplier_match.status == "matched"
    assert proposal.line_matches[0].status == "matched"
    assert svc._pending.get(proposal.proposal_id) is not None


def test_upload_flags_new_supplier_and_article():
    svc = _service(_reader_no_matches)
    proposal = svc.upload(b"%PDF")
    assert proposal.supplier_match.status == "new"
    assert proposal.line_matches[0].status == "new"


def test_upload_blanks_a_supplier_nif_that_fails_the_check_digit():
    # 502267583 is the real misread from scanner_forumsi_1.jpeg: one digit off
    # from the correct 502667583. A reader that WOULD match it, if queried,
    # proves the bad number never reaches the matcher.
    def reader(sql, params):
        if "Entidades" in sql and params.get("tax_id") == "502267583":
            return [{"Chave": 99, "Nome": "WRONG SUPPLIER"}]
        return []

    bill = Bill(supplier_name="Sage", supplier_tax_id="502267583")
    svc = _service(reader)
    svc._parser = FakeParser(bill)
    proposal = svc.upload(b"%PDF")

    assert proposal.bill.supplier_tax_id is None
    assert any("502267583" in w for w in proposal.warnings)
    assert proposal.supplier_match.status != "matched"


def test_upload_leaves_a_valid_nif_untouched_and_warning_free():
    bill = Bill(supplier_name="Sage", supplier_tax_id="502667583")
    svc = _service(_reader_no_matches)
    svc._parser = FakeParser(bill)
    proposal = svc.upload(b"%PDF")

    assert proposal.bill.supplier_tax_id == "502667583"
    assert proposal.warnings == []


def test_upload_leaves_a_spanish_vat_number_untouched():
    bill = Bill(supplier_name="Jotelulu", supplier_tax_id="ESB65814709")
    svc = _service(_reader_no_matches)
    svc._parser = FakeParser(bill)
    proposal = svc.upload(b"%PDF")

    assert proposal.bill.supplier_tax_id == "ESB65814709"
    assert proposal.warnings == []


def test_stage_rejects_unconfirmed_new_records():
    svc = _service(_reader_no_matches)
    proposal = svc.upload(b"%PDF")
    result = svc.stage(proposal.proposal_id, proposal.model_dump(mode="json"))
    assert result["ok"] is False
    assert any("confirm" in v["message"].lower() for v in result["violations"])


def test_stage_rejects_missing_required_total():
    svc = _service(_reader_supplier_and_article)
    proposal = svc.upload(b"%PDF")
    edited = proposal.model_dump(mode="json")
    edited["bill"]["gross_total"] = None
    result = svc.stage(proposal.proposal_id, edited)
    assert result["ok"] is False
    assert any("total" in v["message"].lower() for v in result["violations"])


def test_stage_then_commit_writes_and_audits():
    executor = FakeExecutor()
    svc = _service(_reader_supplier_and_article, executor=executor)
    proposal = svc.upload(b"%PDF")
    staged = svc.stage(proposal.proposal_id, proposal.model_dump(mode="json"))
    assert staged["ok"] is True
    out = svc.commit(proposal.proposal_id, operator="alice")
    assert out["status"] == "ok" and out["document_chave"] == 99
    assert len(executor.calls) == 1
    assert svc._audit.records[0]["status"] == "ok"
    # proposal consumed
    assert svc.commit(proposal.proposal_id, operator="alice")["status"] == "error"


def test_failing_restage_clears_prior_valid_plan():
    executor = FakeExecutor()
    svc = _service(_reader_supplier_and_article, executor=executor)
    proposal = svc.upload(b"%PDF")
    # first stage succeeds and stashes a plan
    assert svc.stage(proposal.proposal_id, proposal.model_dump(mode="json"))["ok"] is True
    # operator edits into an invalid state and re-stages
    edited = proposal.model_dump(mode="json")
    edited["bill"]["gross_total"] = None
    assert svc.stage(proposal.proposal_id, edited)["ok"] is False
    # commit must NOT execute the stale, previously-valid plan
    out = svc.commit(proposal.proposal_id, operator="alice")
    assert out["status"] == "error"
    assert executor.calls == []


def test_failed_stage_clears_a_previously_staged_plan():
    # A ValidationError (not the in-stage violations list) previously returned
    # early, above the plan pop, so a rejected stage left a stale, previously
    # valid plan committable. Distinct from test_failing_restage_clears_
    # prior_valid_plan above: that one fails via the violations list (gross_total
    # is Optional, so model_validate succeeds and the pop already ran); this one
    # fails via BillProposal.model_validate itself raising, the path where the
    # pop used to be skipped.
    executor = FakeExecutor()
    svc = _service(_reader_supplier_and_article, executor=executor)
    proposal = svc.upload(b"%PDF-fake")
    edited = proposal.model_dump(mode="json")
    assert svc.stage(proposal.proposal_id, edited)["ok"] is True

    # Second stage fails validation: the UI posts a cleared required field as null.
    edited["bill"]["supplier_name"] = None
    assert svc.stage(proposal.proposal_id, edited)["ok"] is False

    # The stale plan must not survive a rejected stage.
    out = svc.commit(proposal.proposal_id, operator="alice")
    assert out["status"] == "error"
    assert executor.calls == []


def test_stage_rejects_ambiguous_supplier_without_choice():
    svc = _service(_reader_supplier_and_article)
    proposal = svc.upload(b"%PDF")
    edited = proposal.model_dump(mode="json")
    edited["supplier_match"] = {
        "status": "ambiguous", "chave": None,
        "candidates": [{"chave": 1, "label": "A", "score": 1.0},
                       {"chave": 2, "label": "B", "score": 1.0}],
        "proposed_new": None, "confirmed": False}
    result = svc.stage(proposal.proposal_id, edited)
    assert result["ok"] is False
    assert any(("candidate" in v["message"].lower()) or ("pick" in v["message"].lower())
               for v in result["violations"])


def test_stage_rejects_line_match_length_mismatch():
    svc = _service(_reader_supplier_and_article)
    proposal = svc.upload(b"%PDF")
    edited = proposal.model_dump(mode="json")
    # extra bill line with no corresponding line_match
    edited["bill"]["lines"].append({"description": "Ghost", "quantity": "1",
                                    "unit_price": "1", "vat_rate": "23", "total": "1"})
    result = svc.stage(proposal.proposal_id, edited)
    assert result["ok"] is False
    assert any("line" in v["field"].lower() or "line" in v["message"].lower()
               for v in result["violations"])


import base64
import io

import pytest
from PIL import Image

from logic.bills.extract.media import UnsupportedMedia


def _png_bytes(size=(60, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, "PNG")
    return buf.getvalue()


def test_upload_routes_pdf_to_ocr():
    ocr_calls = []
    svc = _service(_reader_no_matches)
    svc._ocr = lambda data: ocr_calls.append(data) or []
    svc.upload(b"%PDF-1.7 fake")
    assert ocr_calls == [b"%PDF-1.7 fake"]
    assert svc._parser.image_calls == []


def test_upload_routes_image_to_vision_and_never_ocrs():
    def _boom(data):
        raise AssertionError("OCR must not run for an image upload")

    svc = _service(_reader_no_matches)
    svc._ocr = _boom
    data = _png_bytes()
    proposal = svc.upload(data)

    assert proposal.proposal_id.startswith("bill_")
    assert len(svc._parser.image_calls) == 1
    media_type, b64 = svc._parser.image_calls[0]
    assert media_type == "image/png"
    assert base64.b64decode(b64) == data


def test_upload_rejects_unsupported_bytes():
    svc = _service(_reader_no_matches)
    with pytest.raises(UnsupportedMedia):
        svc.upload(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 16)


def _confirmed_new_proposal(svc):
    """Upload against an empty DB (supplier and article both 'new') and confirm
    both, so stage() gets past the confirmation gate."""
    proposal = svc.upload(b"%PDF")
    edited = proposal.model_dump(mode="json")
    edited["supplier_match"]["confirmed"] = True
    edited["line_matches"][0]["confirmed"] = True
    return proposal.proposal_id, edited


def test_stage_rebuilds_new_supplier_from_the_edited_bill():
    # The operator corrects a NIF the model misread by one digit. NCont is
    # permanent master data feeding AT/SAF-T, so the corrected value — not the
    # one captured in proposed_new at upload time — must reach the WritePlan.
    svc = _service(_reader_no_matches)
    proposal_id, edited = _confirmed_new_proposal(svc)
    assert edited["supplier_match"]["proposed_new"]["NCont"] == "500100209"

    # 500100306 passes the PT NIF check digit and differs from the upload-time
    # value, so this still proves the rebuild picks up the edited bill (Task
    # 11 adds a separate check-digit guard, tested below, which would reject
    # an invalid replacement like the old 500100299 and mask what this test
    # is actually about).
    edited["bill"]["supplier_tax_id"] = "500100306"
    edited["bill"]["supplier_name"] = "ACME LDA"

    result = svc.stage(proposal_id, edited)
    assert result["ok"] is True
    supplier = result["write_plan"]["supplier"]
    assert supplier["proposed_new"] == {"Nome": "ACME LDA", "NCont": "500100306"}


def test_stage_rebuilds_new_article_from_the_edited_line():
    svc = _service(_reader_no_matches)
    proposal_id, edited = _confirmed_new_proposal(svc)
    edited["bill"]["lines"][0]["description"] = "Widget, 10mm"

    result = svc.stage(proposal_id, edited)
    assert result["ok"] is True
    assert result["write_plan"]["lines"][0]["article"]["proposed_new"] == {
        "Nome": "Widget, 10mm"}


def test_rebuilt_proposed_new_stays_within_the_rule_whitelist():
    # The earlier SQL-identifier fix whitelists proposed_new keys against
    # matching.*.create_columns. Re-deriving must not widen that set.
    svc = _service(_reader_no_matches)
    proposal_id, edited = _confirmed_new_proposal(svc)
    rule = svc._rule
    result = svc.stage(proposal_id, edited)
    plan = result["write_plan"]
    assert set(plan["supplier"]["proposed_new"]) <= set(
        rule.matching.supplier.create_columns)
    assert set(plan["lines"][0]["article"]["proposed_new"]) <= set(
        rule.matching.article.create_columns)


def test_stage_rejects_an_invalid_operator_typed_nif():
    # The upload guard only catches a misread digit the operator hasn't seen
    # yet. If they then retype the NIF as something that still fails the
    # check digit, stage() must catch that too (Task 11) instead of writing
    # it into Entidades.NCont, which feeds AT/SAF-T reporting.
    svc = _service(_reader_no_matches)
    proposal_id, edited = _confirmed_new_proposal(svc)
    edited["bill"]["supplier_tax_id"] = "500100299"  # fails the check digit

    result = svc.stage(proposal_id, edited)

    assert result["ok"] is False
    assert {"field": "supplier_tax_id",
            "message": "supplier tax id '500100299' failed the NIF check digit"
            } in result["violations"]
    assert svc._pending.pop(proposal_id + ":plan") is None


def test_stage_accepts_a_foreign_tax_id_untouched():
    # pt_nif_is_valid returns None (not False) for a non-PT-shaped value such
    # as a Spanish NIF, since it isn't PT's to judge. is False must not
    # misfire as a truthiness check that would also reject None.
    svc = _service(_reader_no_matches)
    proposal_id, edited = _confirmed_new_proposal(svc)
    edited["bill"]["supplier_tax_id"] = "ESB65814709"
    edited["bill"]["supplier_name"] = "Proveedor SA"

    result = svc.stage(proposal_id, edited)

    assert result["ok"] is True
    assert result["write_plan"]["supplier"]["proposed_new"] == {
        "Nome": "Proveedor SA", "NCont": "ESB65814709"}


@pytest.mark.parametrize("name", [None, ""])
def test_stage_reports_a_cleared_required_field_as_a_violation(name):
    # Clearing the supplier name in the UI posts null. That fails Bill
    # validation, and pydantic's ValidationError is not a RuntimeError, so
    # app.py would return a 500 instead of a reviewable violation.
    svc = _service(_reader_supplier_and_article)
    proposal = svc.upload(b"%PDF")
    edited = proposal.model_dump(mode="json")
    edited["bill"]["supplier_name"] = name
    result = svc.stage(proposal.proposal_id, edited)
    assert result["ok"] is False
    assert any("supplier_name" in v["field"] for v in result["violations"])


def test_stage_leaves_proposed_new_alone_for_matched_records():
    svc = _service(_reader_supplier_and_article)
    proposal = svc.upload(b"%PDF")
    result = svc.stage(proposal.proposal_id, proposal.model_dump(mode="json"))
    assert result["ok"] is True
    assert result["write_plan"]["supplier"]["proposed_new"] is None


from logic.bills.extract import at_qr as at_qr_module


def test_upload_prefers_the_qr_supplier_nif_over_the_model(monkeypatch):
    payload = ("A:500100306*B:514380802*C:PT*D:FT*E:N*F:20260601*G:FT1*"
               "I7:100.00*I8:23.00*N:23.00*O:123.00")
    monkeypatch.setattr("logic.bills.service.decode", lambda data: payload)
    svc = _service(_reader_no_matches)
    proposal = svc.upload(b"%PDF-fake")
    assert proposal.bill.supplier_tax_id == "500100306"
    assert any("QR code reads" in w for w in proposal.warnings)


def test_upload_is_unchanged_when_no_qr_is_present(monkeypatch):
    monkeypatch.setattr("logic.bills.service.decode", lambda data: None)
    svc = _service(_reader_no_matches)
    proposal = svc.upload(b"%PDF-fake")
    # _bill()'s fixture NIF survives untouched.
    assert proposal.bill.supplier_tax_id == "500100209"
    assert all("QR code" not in w for w in proposal.warnings)


def test_upload_ignores_a_qr_that_is_not_an_at_code(monkeypatch):
    monkeypatch.setattr("logic.bills.service.decode",
                        lambda data: "https://example.com/some-other-qr")
    svc = _service(_reader_no_matches)
    assert svc.upload(b"%PDF-fake").bill.supplier_tax_id == "500100209"


def test_upload_keeps_arithmetic_warnings_alongside_qr_warnings(monkeypatch):
    payload = ("A:500100209*D:FT*E:A*F:20260601*G:FT1*N:23.00*O:123.00")
    monkeypatch.setattr("logic.bills.service.decode", lambda data: payload)
    svc = _service(_reader_no_matches)
    warnings = svc.upload(b"%PDF-fake").warnings
    assert any("cancel" in w.lower() for w in warnings)


def _reader_only_known_nif(sql, params):
    """Only 500100209 exists in Entidades. 500100306 does not."""
    if "Entidades" in sql and params.get("tax_id") == "500100209":
        return [{"Chave": 7, "Nome": "ACME"}]
    return []


def _staged_edit(proposal, **bill_over):
    edited = proposal.model_dump(mode="json")
    edited["bill"].update(bill_over)
    edited["supplier_match"]["confirmed"] = True
    for lm in edited["line_matches"]:
        lm["confirmed"] = True
    return edited


def test_stage_rematches_a_corrected_nif_instead_of_creating_a_duplicate():
    """The operator fixes a misread NIF to one that already exists in Entidades.

    The match was decided at upload from the model's wrong value, so it says
    'new'. If stage() does not recompute it, the executor inserts a second
    supplier row for a company we already have — permanent master data, and
    NCont feeds AT/SAF-T.
    """
    svc = _service(_reader_only_known_nif)
    svc._parser = FakeParser(_bill().model_copy(update={"supplier_tax_id": "500100306"}))
    proposal = svc.upload(b"%PDF-fake")
    assert proposal.supplier_match.status == "new"  # nothing matched the misread NIF

    out = svc.stage(proposal.proposal_id, _staged_edit(proposal, supplier_tax_id="500100209"))

    assert out["ok"] is True, out
    supplier = out["write_plan"]["supplier"]
    assert supplier["status"] == "matched"
    assert supplier["chave"] == 7
    assert supplier["proposed_new"] is None


def test_stage_still_creates_when_the_corrected_nif_matches_nothing():
    """Re-matching must not break the ordinary create path."""
    svc = _service(_reader_only_known_nif)
    svc._parser = FakeParser(_bill().model_copy(update={"supplier_tax_id": "500100306"}))
    proposal = svc.upload(b"%PDF-fake")

    out = svc.stage(proposal.proposal_id, _staged_edit(proposal, supplier_tax_id="500100403"))

    assert out["ok"] is True, out
    supplier = out["write_plan"]["supplier"]
    assert supplier["status"] == "new"
    # proposed_new carries the EDITED value, not the upload-time one
    assert supplier["proposed_new"]["NCont"] == "500100403"
    # the operator's confirmation survives the re-match, or they would be told
    # to confirm again on every stage
    assert supplier["confirmed"] is True


def _reader_ambiguous_supplier(sql, params):
    if "Entidades" in sql and "LIKE" in sql:
        return [{"Chave": 5, "Nome": "ACME LDA"}, {"Chave": 6, "Nome": "ACME SA"}]
    if "Artigos" in sql:
        return [{"Chave": 42, "Nome": "Widget"}]
    return []


def test_stage_does_not_rematch_a_candidate_the_operator_picked():
    """'ambiguous' carries a deliberate choice made on the review screen.

    Re-running the match would recompute it from scratch and silently discard
    which of the candidates the operator selected, so only 'new' is recomputed.
    """
    svc = _service(_reader_ambiguous_supplier)
    svc._parser = FakeParser(_bill().model_copy(update={"supplier_tax_id": None}))
    proposal = svc.upload(b"%PDF-fake")
    assert proposal.supplier_match.status == "ambiguous"

    edited = proposal.model_dump(mode="json")
    edited["supplier_match"]["chave"] = 6          # operator picks ACME SA
    out = svc.stage(proposal.proposal_id, edited)

    assert out["ok"] is True, out
    assert out["write_plan"]["supplier"]["status"] == "ambiguous"
    assert out["write_plan"]["supplier"]["chave"] == 6
