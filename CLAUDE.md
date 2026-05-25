# ERP Agent — AI-Native ERP Solution

## Project Overview

An AI-native ERP system built around three tightly integrated layers: a voice-driven adaptive UI, an AI-powered business logic engine, and a robust data management layer. The system is designed so that AI is not a feature bolted on top — it is the core mechanism through which users interact with and the system enforces business rules.

## Architecture

### 1. Adaptive UI Layer

The UI is minimal and dynamic — it exists to surface the right inputs and outputs at the right moment based on user intent. It does **not** contain business logic.

**Responsibilities:**
- Accept voice commands and natural language input from users
- Translate intent into structured actions (insert, update, delete, query, report)
- Render forms, confirmations, and data views dynamically based on context
- Guide users step-by-step through ERP workflows (e.g., creating a sale, generating an invoice)
- Display reports and query results clearly

**Design principles:**
- The UI adapts to the task, not the other way around — screens are composed on demand
- Voice is the primary input modality; text fallback is always available
- Minimize clicks: the AI pre-fills what it can, the user confirms

### 2. Business Logic Layer (AI-Native Core)

This is the most critical component. Business rules are not hard-coded — they are encoded in a set of **enterprise documents** (structured prompts, rule definitions, validation schemas) that the AI uses to reason over every transaction and request.

**Responsibilities:**
- Interpret user intent and map it to valid ERP operations
- Load and apply the relevant enterprise document(s) for the current workflow
- Validate data against business rules before any write hits the database
- Detect conflicts, missing fields, or policy violations and surface them to the user
- Generate documents such as invoices, purchase orders, and reports

**Enterprise documents:**
- Stored as structured files (e.g., YAML, JSON, or Markdown with schema) in `business_rules/`
- Each document covers one domain: sales, procurement, inventory, invoicing, payroll, etc.
- The AI reads these documents at runtime as part of its system context — changing a rule means editing a document, not touching code
- Documents must be versioned; breaking changes require a migration note

**Active domains:**

| Domain | Document | Status |
|---|---|---|
| Payroll | [business_rules/payroll.yaml](business_rules/payroll.yaml) | Active |

**Design principles:**
- No business logic lives in the UI or the database layer — only here
- Every write operation must pass through this layer; direct DB writes are never allowed from the UI
- The AI must always cite which rule or document it applied when making a decision

### 3. Database Management Layer

Handles all persistence. The business logic layer calls this layer; the UI never does so directly.

**Responsibilities:**
- Execute all CRUD operations against the underlying database
- Enforce referential integrity and schema constraints
- Expose a typed, validated API (not raw SQL) to the business logic layer
- Manage transactions — all multi-step operations must be atomic
- Support audit logging: every insert, update, and delete is logged with timestamp, user, and the business rule that authorized it

**Design principles:**
- Schema changes require a migration script — never mutate the schema manually
- The data layer is agnostic to business rules; it trusts the layer above has already validated
- Read operations (reports, queries) may bypass the business logic layer but must still go through this layer's API

## Directory Structure (intended)

```
ERP_Agent/
├── CLAUDE.md
├── business_rules/        # Enterprise documents (YAML/JSON/MD)
│   ├── payroll.yaml       ✓ active
│   ├── sales.yaml
│   ├── invoicing.yaml
│   ├── procurement.yaml
│   └── ...
├── ui/                    # Adaptive frontend
│   └── payroll/           ✓ scaffolded
├── logic/                 # AI business logic engine
│   └── payroll/           ✓ scaffolded
├── db/                    # Database access layer
│   ├── migrations/
│   └── ...
└── tests/
    └── payroll/           ✓ scaffolded
```

## Key Constraints

- **AI is authoritative for business logic** — do not hard-code rules in application code that belong in a business rule document
- **No direct database access from the UI** — all writes flow: UI → logic → db
- **Audit trail is non-negotiable** — every data mutation must be traceable
- **Voice commands must degrade gracefully** — if speech-to-text fails, text input takes over without breaking the flow
- **Enterprise documents are the source of truth** for what is and is not a valid ERP operation; when in doubt, consult or update the relevant document

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| API framework | FastAPI + Uvicorn |
| AI engine | Anthropic SDK (`anthropic`) — Claude Sonnet 4.6 |
| Data models | Pydantic v2 |
| Rule documents | YAML (`pyyaml`) |
| Tests | pytest + pytest-asyncio |
| HTTP test client | httpx |

Run the server: `uvicorn logic.main:app --reload`
Run tests: `pytest tests/`
Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.

## Development Notes

- When adding a new ERP domain (e.g., payroll), create the enterprise document first, then implement the logic and db layers, then wire up the UI last
- Tests for the business logic layer should cover both valid and invalid inputs, and assert which rule was applied
- Keep the AI's system prompt for each workflow thin — load the enterprise document dynamically rather than duplicating rules into prompts
