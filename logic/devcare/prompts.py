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
            "entity": {"type": "string",
                       "description": "the entity name, exactly as listed in the system prompt"},
            "operation": {"type": "string", "enum": ["create", "update", "delete"]},
            "fields": {"type": "object", "description": "field name -> value"},
            "target_pk": {"type": ["integer", "null"]},
        },
        "required": ["entity", "operation", "fields"],
    },
}

PRESENT_FORM_TOOL: dict = {
    "name": "present_form",
    "description": (
        "Show the operator a data-entry FORM for creating or updating a record of "
        "one entity, instead of asking for fields one by one. The UI renders the "
        "right input per field (date pickers, dropdowns for gender/specialty, number "
        "fields). Use this as the FIRST step whenever the operator wants to create or "
        "edit a record. Pass `prefill` for any values the operator already mentioned "
        "(map field name -> value). For update, pass target_pk (resolved via lookup). "
        "After the form is shown, the operator fills and submits it themselves — you "
        "do not need to call propose_change for create/update."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity": {"type": "string",
                       "description": "the entity name, exactly as listed in the system prompt"},
            "operation": {"type": "string", "enum": ["create", "update"]},
            "prefill": {"type": "object",
                        "description": "field name -> value the operator already provided"},
            "target_pk": {"type": ["integer", "null"]},
        },
        "required": ["entity", "operation"],
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
- To CREATE or UPDATE a record, call `present_form` FIRST. This shows the operator \
a data-entry form with the right input for every field (date pickers, gender and \
specialty dropdowns, number fields). Do not ask for fields one by one. If the \
operator already mentioned some values, pass them as `prefill`. Only `name` (and a \
couple of required fields) must end up filled; all other fields are recommended but \
optional, and the operator fills the form themselves and submits it — you do NOT \
call propose_change for create/update.
- For UPDATE, first use `lookup` to find the exact row's Chave, then call \
`present_form` with that target_pk so the form is pre-filled with current values.
- For DELETE, use `lookup` to find the row, then `propose_change` with \
operation=delete and target_pk. (Deletes are soft-deletes and need no form.)
- Use the `lookup` tool (read-only SELECT) to resolve references and find rows.
- You CANNOT commit. Only the operator can, by clicking Confirm on the preview that \
appears after they submit the form. Briefly tell them to fill in the form and confirm.
- If validation returns violations, explain them plainly and ask for corrections.
- Never invent column names or tables outside the list above.

Reply to the operator in plain, friendly text.
"""
