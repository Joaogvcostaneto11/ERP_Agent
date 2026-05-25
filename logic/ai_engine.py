"""
Core AI reasoning engine.

Every call loads the enterprise document for the requested domain as a
prompt-cached block, then asks the model to reason over the user intent.
The enterprise document is static per domain, so cache hits are near-certain
after the first request.
"""
import json
import re

import anthropic

from logic.config import settings
from logic.rule_loader import rule_as_text

if not settings.anthropic_api_key:
    raise EnvironmentError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

_SYSTEM_ROLE = """\
You are the business logic engine for an AI-native ERP system.
You enforce business rules exactly as defined in the enterprise document provided.
Always cite the exact rule section (e.g., "payroll.yaml §permissions") when making a decision.
Return ONLY a JSON object — no prose, no markdown fences outside the object.

Required response shape:
{
  "action": "<action_id>",
  "parameters": { ... },
  "rule_applied": "<document §section>",
  "explanation": "<one sentence>"
}
"""


def reason(domain: str, user_intent: str, context: dict) -> dict:
    """
    Send user_intent + context to the model with the domain enterprise document
    as cached system context. Returns a structured decision dict.
    """
    rule_text = rule_as_text(domain)

    response = _client.messages.create(
        model=settings.model,
        max_tokens=1024,
        system=[
            {"type": "text", "text": _SYSTEM_ROLE},
            {
                "type": "text",
                "text": f"ENTERPRISE DOCUMENT — {domain}:\n\n{rule_text}",
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Intent: {user_intent}\n\n"
                    f"Context: {json.dumps(context, default=str)}"
                ),
            }
        ],
    )

    raw = response.content[0].text.strip()
    # Strip accidental markdown fences if the model adds them
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    return json.loads(match.group(1) if match else raw)
