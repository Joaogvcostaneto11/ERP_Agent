from __future__ import annotations

LOOKUP_TOOL: dict = {
    "name": "lookup",
    "description": (
        "Run a single read-only SELECT against DevCare to find rows, resolve "
        "references, or fetch the current values of a row you are about to update. "
        "Use 3-part names like DevCare.dbo.Entidades."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"sql": {"type": "string"}},
        "required": ["sql"],
    },
}

PROPOSE_CHANGE_TOOL: dict = {
    "name": "propose_change",
    "description": (
        "Validate and STAGE a single create/update/delete on one entity. This does "
        "NOT write anything — it returns a preview the operator must confirm. For "
        "update/delete you must include target_pk (the Chave of the row, resolved "
        "via lookup first)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity": {"type": "string", "description": "patient or specialty"},
            "operation": {"type": "string", "enum": ["create", "update", "delete"]},
            "fields": {"type": "object", "description": "field name -> value"},
            "target_pk": {"type": ["integer", "null"]},
        },
        "required": ["entity", "operation", "fields"],
    },
}


def build_system(entities_doc: str, operator: str) -> str:
    return f"""\
You are the DevCare operations assistant. The operator is **{operator}**. You help \
them create, update, and (soft-)delete records in the DevCare database through \
conversation.

You can act ONLY on these entities, with exactly these writable fields:

{entities_doc}

How to work:
- Understand the operator's intent. Ask for any required fields that are missing, \
one or two at a time. Be concise.
- Use the `lookup` tool (read-only SELECT) to resolve references (e.g. find a \
specialty's Chave) and, for updates/deletes, to find the exact row and show its \
current values.
- When you have everything, call `propose_change`. This validates and stages the \
change and shows the operator a preview. It does NOT write.
- You CANNOT commit. Only the operator can, by clicking Confirm on the preview. \
After you propose, tell them to review and confirm.
- If validation returns violations, explain them plainly and ask for corrections.
- Never invent column names or tables outside the list above.

Reply to the operator in plain, friendly text.
"""
