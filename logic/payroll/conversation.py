"""
Multi-turn conversational engine for payroll operations.

Session message history is kept server-side. Claude uses tool use to execute
actions only when all required fields are collected — asking follow-up questions
until it has everything it needs.
"""
import json
import uuid
from typing import Optional

import anthropic

from logic.config import settings
from logic.rule_loader import rule_as_text

_client: Optional[anthropic.Anthropic] = None
_sessions: dict[str, list[dict]] = {}

_TOOLS = [
    {
        "name": "create_employee",
        "description": (
            "Persist a new employee to the database. Call this only when you have "
            "confirmed all required fields with the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Unique employee ID (e.g. EMP001). Suggest one if the user doesn't specify.",
                },
                "name": {"type": "string", "description": "Employee full name"},
                "type": {
                    "type": "string",
                    "enum": ["salaried", "hourly", "contractor"],
                },
                "pay_period": {
                    "type": "string",
                    "enum": ["weekly", "biweekly", "monthly"],
                },
                "annual_salary": {
                    "type": "number",
                    "description": "Annual gross salary in USD. Required when type is 'salaried'.",
                },
                "hourly_rate": {
                    "type": "number",
                    "description": "Hourly rate in USD. Required when type is 'hourly'.",
                },
                "deduction_elections": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["health_insurance", "retirement_plan"]},
                    "description": "Voluntary deduction elections (optional).",
                },
            },
            "required": ["id", "name", "type", "pay_period"],
        },
    }
]

_SYSTEM = """\
You are a friendly, concise ERP payroll assistant. You guide users through \
payroll operations step by step via natural conversation.

When a user asks to create an employee, collect the following one or two fields \
at a time — never dump all questions at once:
  1. Full name
  2. Employee ID (suggest EMP001, EMP002, etc. if the user doesn't have one)
  3. Employment type: salaried, hourly, or contractor
  4. Pay period: weekly, biweekly, or monthly
  5. Annual salary (if salaried) OR hourly rate (if hourly)
  6. Optional deductions: health insurance, retirement plan (ask once at the end)

Once you have all required fields confirmed, call create_employee immediately — \
do not ask "shall I proceed?". After the tool call succeeds, confirm to the user \
in one friendly sentence.

Keep every reply short. Never repeat information the user already gave.\
"""


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def converse(session_id: Optional[str], message: str, user_id: str, role: str) -> dict:
    """
    Process one user turn. Maintains conversation history server-side keyed by session_id.
    Returns {"session_id": str, "reply": str, "action_taken": dict | None}.
    """
    if not session_id or session_id not in _sessions:
        session_id = str(uuid.uuid4())
        _sessions[session_id] = []

    history = _sessions[session_id]
    history.append({"role": "user", "content": message})

    rule_text = rule_as_text("payroll")
    system = [
        {"type": "text", "text": _SYSTEM},
        {
            "type": "text",
            "text": f"PAYROLL ENTERPRISE DOCUMENT:\n\n{rule_text}",
            "cache_control": {"type": "ephemeral"},
        },
    ]

    client = _get_client()
    response = client.messages.create(
        model=settings.model,
        max_tokens=1024,
        system=system,
        tools=_TOOLS,
        messages=history,
    )

    action_taken = None

    if response.stop_reason == "tool_use":
        assistant_content = _serialize_content(response.content)
        history.append({"role": "assistant", "content": assistant_content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = _execute_tool(block.name, block.input)
                action_taken = {"tool": block.name, "input": block.input, "result": result}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

        history.append({"role": "user", "content": tool_results})

        follow_up = client.messages.create(
            model=settings.model,
            max_tokens=512,
            system=system,
            tools=_TOOLS,
            messages=history,
        )
        reply = _extract_text(follow_up)
        history.append({"role": "assistant", "content": reply})
    else:
        reply = _extract_text(response)
        history.append({"role": "assistant", "content": reply})

    return {"session_id": session_id, "reply": reply, "action_taken": action_taken}


def _execute_tool(name: str, inputs: dict) -> dict:
    if name == "create_employee":
        from db.database import session_scope
        from db.repositories.employees import EmployeeRepository
        from db.repositories.audit import AuditRepository
        from logic.payroll import validator
        from logic.payroll.models import Employee

        emp = Employee(**inputs)
        errors = validator.validate_employee(emp)
        if errors:
            return {"status": "error", "message": errors[0]}

        with session_scope() as db:
            repo = EmployeeRepository(db)
            if repo.exists(emp.id):
                return {"status": "error", "message": f"Employee '{emp.id}' already exists"}
            created = repo.create(emp)
            AuditRepository(db).log(
                user_id="ui-user",
                action="create",
                entity_type="employee",
                entity_id=created.id,
                rule_applied="payroll.yaml §employee_types",
                rule_version="1.0.0",
                details={"name": created.name, "type": created.type},
            )

        return {"status": "created", "employee_id": created.id, "name": created.name}

    raise ValueError(f"Unknown tool: {name}")


def _serialize_content(content) -> list[dict]:
    result = []
    for block in content:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return result


def _extract_text(response) -> str:
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""
