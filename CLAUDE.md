# ERP Agent — AI-Native ERP Solution

## Project Overview

An AI-native ERP system built around three tightly integrated layers: an adaptive conversational UI, an AI-powered business logic engine, and a robust data management layer. The system is designed so that AI is not a feature bolted on top — it is the core mechanism through which users interact with and the system enforces business rules.

## Architecture

### 1. Adaptive UI Layer

The UI is minimal and dynamic — it exists to surface the right inputs and outputs at the right moment based on user intent. It does **not** contain business logic.

**Responsibilities:**
- Accept natural language input from users
- Translate intent into structured actions (insert, update, delete, query, report)
- Render forms, confirmations, and data views dynamically based on context
- Guide users step-by-step through ERP workflows (e.g., creating a sale, generating an invoice)
- Display reports and query results clearly

**Design principles:**
- The UI adapts to the task, not the other way around — screens are composed on demand
- Text is the primary input modality
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
| DevCare CRUD | [business_rules/devcare/](business_rules/devcare/) (patient, specialty, doctor) | Active (writes) |
| Bill ingestion | [business_rules/bills/](business_rules/bills/) (purchase_invoice) | Active (draft writes) |

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
**Gate secrets fail closed when deployed.** All three services take a shared-password HTTP Basic gate (`APP_PASSWORD`, `BILLS_APP_PASSWORD`, `DEVCARE_APP_PASSWORD` — three separate secrets on purpose). Unset means ungated, which is intended for local dev only: when `RENDER`/`RENDER_SERVICE_ID` is present the service **refuses to start** without one, because those secrets are typed into the Render dashboard by hand and a blank field would otherwise publish an ungated service that writes to the ERP database.

Run the chat UI server: `uvicorn logic.chat.app:app --reload`, then open http://localhost:8000/.
The chat UI requires `ANTHROPIC_API_KEY` and a `DATABASE_URL` pointing at a read-only SQL Server login. Set `APP_PASSWORD` to gate it.
Run the DevCare operations (write CRUD) server: `uvicorn logic.devcare.app:app --reload --port 8001`, then open http://localhost:8001/.
DevCare CRUD requires `ANTHROPIC_API_KEY`, `DATABASE_URL` (read-only, for lookups), and `DEVCARE_WRITE_DATABASE_URL` (a writable login; ideally scoped to DevCare's curated tables). Set `DEVCARE_APP_PASSWORD` to put the service behind an HTTP Basic gate — unset leaves it **ungated**, which is fine on a laptop only. It is a separate secret from `APP_PASSWORD` and `BILLS_APP_PASSWORD`. Writes only touch the registered entities in `business_rules/devcare/` and require explicit operator confirmation.
Run the Bill ingestion server: `uvicorn logic.bills.app:app --reload --port 8002`, then open http://localhost:8002/.
Bill ingestion requires `ANTHROPIC_API_KEY`, `DATABASE_URL` (read-only, for lookups), `BILLS_WRITE_DATABASE_URL` (a writable login for the ERP database, currently DevDB; writes land in whatever database that URL names), and the Tesseract + Poppler binaries (`tesseract-ocr`, `tesseract-ocr-por`, `poppler-utils`). QR decoding additionally needs `opencv-python-headless`. Set `BILLS_APP_PASSWORD` to put the service behind an HTTP Basic gate — unset leaves it **ungated**, which is fine on a laptop only. It is deliberately a different secret from the chat service's `APP_PASSWORD`. Set `BILLS_ADMIN_TOKEN` (sent as `X-Admin-Token`) to enable the admin write-mapping panel — unset leaves every `/admin/rules*` route returning 404 and the panel hidden. This is a third, separate secret: an operator may use the service without being able to change how invoices map onto database columns. Before first deploy, run `db/migrations/002_bills_audit.sql` and `db/migrations/003_bills_rules.sql` against the write database: the audit row is inserted in the same transaction as the document, so a missing table fails every commit, and the rule document is now read from `ERPAgent_BillRules` rather than from disk. `business_rules/bills/purchase_invoice.yaml` is the **seed** for that table — it supplies version 1 into an empty table and is never written back to, because Render's filesystem is ephemeral and in-place rewrites reverted on every deploy. An unreadable rule table is a 503, not a fallback to the packaged YAML. Accepted bills are written as draft, uncertified `Doc001` documents.

## Development Notes

### Development Principles
1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.
2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

Before you do any work, mention how you could verify that work.

3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### Development Logic
- When adding a new ERP domain (e.g., payroll), create the enterprise document first, then implement the logic and db layers, then wire up the UI last
- Tests for the business logic layer should cover both valid and invalid inputs, and assert which rule was applied
- Keep the AI's system prompt for each workflow thin — load the enterprise document dynamically rather than duplicating rules into prompts

### Development verification
Please go back and verify all your work so far. 
Make sure you used best practise, were efficient and didn't introduce any issues. 
