# How ERP Agent Works

## The Core Idea

ERP Agent is an AI-native ERP system. The key distinction from a traditional ERP is that **business rules are not hard-coded** — they live in plain YAML documents, and an AI model reads those documents at runtime to reason about every operation. Changing a business rule means editing a file, not shipping code.

The system has three layers that work together:

```
User (voice / text)
        ↓
  [ UI Layer ]          ← chat interface, renders forms dynamically
        ↓
  [ Logic Layer ]       ← AI engine + rule validation + orchestration
        ↓
  [ Database Layer ]    ← PostgreSQL via SQLAlchemy + audit trail
```

Data always flows top to bottom. The UI never touches the database directly. Every write goes through the logic layer first.

---

## Layer 1 — The UI

The interface is a minimal chat window served at `http://localhost:8000`. It is intentionally thin — it has no business logic whatsoever.

The user selects a role (HR Manager, Finance Director, Employee, Auditor) and types a request in plain language:

> "Create new employee"
> "Run payroll for May 2026"
> "Show me the payslip for EMP001"

Every message is sent as a POST to `/payroll/converse`. The UI keeps a `session_id` returned by the first response and sends it back with every subsequent message so the server knows which conversation it belongs to.

When the server completes an action (e.g. saves a new employee), it returns `action_taken` alongside the reply. The UI renders this as a green success card showing the saved field values.

Voice input is architecturally supported — the microphone button is wired up and ready, the speech-to-text pipeline is the next step to connect.

---

## Layer 2 — The Business Logic Layer

This is the most important layer. It has three sub-components:

### 2a. Enterprise Documents

Business rules live in `business_rules/` as YAML files. There is one file per ERP domain:

```
business_rules/
└── payroll.yaml     ← active
```

`payroll.yaml` defines everything the system needs to know about payroll:

- **Employee types** — salaried (annual salary ÷ pay periods), hourly (with 1.5× overtime above 40h/week), contractor (excluded from standard payroll entirely)
- **Pay periods** — weekly (52/year), biweekly (26/year), monthly (12/year)
- **Deductions** — mandatory (income tax 20%, social security 8%) applied before optional ones (health insurance, retirement plan); total deductions can never exceed gross pay
- **5-step payroll run workflow** — collect → calculate → review → commit → disburse
- **Permissions** — which roles can do what (e.g. only `finance_director` can approve a run)
- **Audit requirements** — 7-year retention, every write must be logged with the rule version that authorized it

Changing a rule — say, raising the overtime multiplier from 1.5× to 2× — means editing one line in `payroll.yaml`. No code changes required.

### 2b. The AI Engine

`logic/ai_engine.py` wraps the Anthropic Claude API. Every time the AI is called for a domain:

1. The enterprise document is loaded from disk (cached after first read)
2. It is sent to Claude as a **prompt-cached system block** — meaning on repeated calls within a 5-minute window, the model reads the document from cache rather than re-processing it, which saves both cost and latency
3. Claude reasons about the user's request against those rules and returns a structured JSON decision that always includes which rule section was applied

### 2c. The Conversational Engine

`logic/payroll/conversation.py` handles multi-turn conversations. When a user says "create new employee", the system does not ask for all fields at once. Instead:

1. A session is created server-side (keyed by a UUID returned to the browser)
2. The full message history is kept on the server and sent to Claude on every turn
3. Claude is given a `create_employee` **tool** — a structured function it can call only when it has collected all required fields
4. Claude asks for fields one or two at a time, naturally, until it has: name, employee ID, employment type, pay period, and salary/rate
5. Once Claude decides it has enough information, it calls `create_employee` automatically — no "shall I proceed?" confirmation
6. The tool execution calls the database layer, writes the record, logs an audit entry, and returns a success result
7. Claude gets the tool result and confirms to the user in one sentence

The conversation history is preserved across turns so Claude never asks for information the user already gave.

### 2d. Rule Validation

Before any data reaches the database, `logic/payroll/validator.py` runs pre-flight checks derived from the enterprise document:

- Contractors are blocked from standard payroll (`§employee_types`)
- Hourly employees must have an approved time record before a payroll run starts (`§payroll_run.step1`)
- No employee can appear twice in the same run (`§payroll_run.step1`)
- Each role is checked against the permissions table before sensitive actions (`§permissions`)
- Net pay is checked against the minimum wage floor (`§compensation.salary`)

Every error message cites the exact YAML section that triggered it, so the user sees *why* something was rejected, not just *that* it was.

---

## Layer 3 — The Database Layer

`db/` handles all persistence. The logic layer calls repositories; nothing else touches the database.

### Schema (5 tables)

| Table | Purpose |
|---|---|
| `employees` | Employee master data |
| `payroll_runs` | One record per payroll run, with status tracking |
| `payslips` | One record per employee per run |
| `payslip_lines` | Individual earning and deduction line items per payslip |
| `audit_log` | Append-only log of every write, with the rule that authorized it |

Schema changes are managed by **Alembic** migrations in `db/alembic/versions/`. Never edit the schema manually — always create a new migration file.

### Audit Trail

Every write operation records an entry in `audit_log` in the **same database transaction** as the write itself. The audit table has no update or delete methods — it is append-only by design. Each entry captures:

- Who performed the action (`user_id`)
- What happened (`action`, `entity_type`, `entity_id`)
- Which rule authorized it (`rule_applied`, `rule_version`)
- A JSON details blob with relevant values

---

## Worked Example — Creating an Employee

Here is exactly what happens when a user types "create new employee":

```
Browser  →  POST /payroll/converse  { message: "create new employee", session_id: null }
                    ↓
         conversation.py creates a new session (UUID)
         Appends user message to session history
                    ↓
         Calls Claude with:
           - System: conversational assistant instructions
           - System (cached): full payroll.yaml text
           - Tool: create_employee (schema of required fields)
           - Messages: [{ role: "user", content: "create new employee" }]
                    ↓
         Claude replies: "Sure! What's the employee's full name?"
                    ↓
Browser  ←  { session_id: "abc-123", reply: "Sure! What's the employee's full name?" }
```

The user answers. The browser sends the next message with the same `session_id`. This repeats until Claude has all the fields. Then:

```
         Claude decides it has all required information
         Claude calls the create_employee tool with:
           { id: "EMP001", name: "Alice", type: "salaried",
             pay_period: "monthly", annual_salary: 60000 }
                    ↓
         _execute_tool() in conversation.py:
           1. Validates the Employee model (Pydantic)
           2. Runs validator.validate_employee() against payroll.yaml rules
           3. Opens a DB session via session_scope()
           4. EmployeeRepository.create() → INSERT INTO employees
           5. AuditRepository.log() → INSERT INTO audit_log
           6. session_scope() commits both in one transaction
                    ↓
         Tool result { status: "created", employee_id: "EMP001", name: "Alice" }
         is sent back to Claude
                    ↓
         Claude replies: "Alice has been added as a salaried employee (EMP001)."
                    ↓
Browser  ←  { reply: "Alice has been added...", action_taken: { tool: "create_employee", ... } }
```

The browser renders the reply as a chat bubble and the `action_taken` payload as a green card showing all the saved fields.

---

## Payroll Run Workflow

Once employees exist, a payroll run follows the 5 steps defined in `payroll.yaml §payroll_run`:

| Step | Endpoint | Who | What happens |
|---|---|---|---|
| 1 + 2 | `POST /payroll/runs` | HR Manager | Collect inputs, validate rules, calculate gross/deductions/net for every employee. Run is created in `review` status. |
| 3 | `POST /payroll/runs/{id}/approve` | Finance Director | Role-checked against `§permissions`. Status moves to `committed`. |
| 4 + 5 | `POST /payroll/runs/{id}/commit` | System | Audit log entry written per payslip. Status moves to `disbursed`. Run is now immutable. |

If an error is found after a run is committed, an **adjustment run** is created via `POST /payroll/adjustments`. It records only the delta against the original run. Direct edits to closed periods are forbidden by the rule engine.

---

## Adding a New ERP Domain

The architecture is designed to grow one domain at a time. To add, say, an **invoicing** module:

1. Create `business_rules/invoicing.yaml` with the domain rules
2. Implement `logic/invoicing/` (models, calculator, validator, engine, router)
3. Add `db/alembic/versions/0002_invoicing_schema.py` migration
4. Register the router in `logic/main.py`
5. Update the UI to support invoicing intents

The AI engine picks up the new document automatically — no changes to the AI integration code are needed.

---

## Running the App

```bash
# 1. Copy and fill in credentials
cp .env.example .env

# 2. Create the PostgreSQL database
psql -U postgres -c "CREATE DATABASE erp_agent;"

# 3. Run migrations
.venv\Scripts\alembic upgrade head

# 4. Start the server
.venv\Scripts\uvicorn logic.main:app --reload

# 5. Run tests (no DB or API key required)
.venv\Scripts\pytest tests/
```

Open `http://localhost:8000` and start talking to the system.
