# Payroll Module — Business Logic Layer Design

**Status:** Draft, awaiting user approval
**Date:** 2026-05-26
**Scope:** Business logic layer of the payroll module, v1 core engine
**Jurisdiction:** Portugal (industry-agnostic)
**Architecture:** Deterministic engine + AI orchestration; rules in layered YAML

---

## 1. Overview

The payroll module computes gross-to-net pay for Portuguese employees, period by period, with rules sourced from layered YAML documents. The business logic layer is the only place writes happen — the UI calls `PayrollService`, the AI calls the same service through tool wrappers, and the DB layer is invoked only by the service via injected repositories.

The design is shaped by three commitments from the project's `CLAUDE.md`:

1. **Rules live in enterprise documents.** Changing a rule means editing YAML, not code.
2. **The AI must cite which rule it applied** for every decision.
3. **Every write passes through the business logic layer** — no direct DB writes from the UI, no business logic embedded in primitives or repositories.

The design also reflects a fourth pragmatic principle: **the LLM never does arithmetic.** Math lives in Python primitives that operate on `Decimal` values; the AI orchestrates and narrates.

## 2. Goals & Non-Goals

### Goals (v1)

- Compute periodic payslips (gross → deductions → net) for any Portuguese employee on a CT, CTT, CTI, part-time, or internship contract.
- Support arbitrary industries via Collective Bargaining Agreement (CCT/IRCT) overrides loaded as YAML.
- Support monthly, biweekly, and weekly pay frequencies (monthly is the primary target; the engine is frequency-agnostic).
- Produce a per-line audit trail citing the YAML clauses that authorized each number.
- Reproduce historical payrolls deterministically: same inputs + same rule stack → identical numbers, indefinitely.
- Expose a small, typed Python API (`PayrollService`) that both the UI and AI consume; the AI through tool wrappers.

### Non-Goals (v1) — each gets its own follow-up spec

- Off-cycle / extraordinary runs (bonuses, severance, mid-period termination payments).
- Retroactive corrections crossing closed periods.
- Statutory filings (Modelo 10, DMR-AT, DMR-SS).
- Banking / SEPA payment file generation.
- UI integration and voice flows.
- Database schema and migrations (only the repository *interfaces* are defined here).
- Multi-tenant SaaS scoping. The data model supports multiple `Company` entities within one service instance (so company-layer YAML applies per `company_id`), but tenant isolation across organizations — auth, data partitioning, per-tenant rule overrides — is not in scope.
- Mid-period contract changes (rejected at `update_contract`; future spec).

## 3. Architectural Approach

**Hybrid: Python compensation primitives + YAML composition + layered rule resolver.**

Python implements a small library of deterministic compensation primitives (`IRSWithholdingTable`, `TSUContribution`, `SubsidioFeriasAccrual`, `MealAllowance`, `OvertimeCalculator`, `Prorate`, `RoundingPolicy`, etc.). Each primitive is a typed, tested unit doing exactly one calculation.

YAML enterprise documents compose primitives into rules: which components apply, with what parameters, in what order, under which conditions. The composition is layered, and a deterministic resolver merges the layers into a `CalculationPlan` for a given `(employee, period)` pair.

The AI orchestrates: parses intent, validates inputs against rules, executes the engine through tools, narrates results, and cites the YAML clauses that authorized each number. It never produces a monetary value itself.

Trade-offs accepted: a genuinely new statutory mechanism (e.g., a brand-new tax) requires adding a primitive in code. Everything else — new components, CCT-specific rules, company policies, parameter changes — is YAML only.

## 4. Module Structure

```
logic/payroll/
├── public/                    Public API — only thing UI/other domains import
│   ├── service.py             PayrollService: orchestrator, single entry point
│   └── schemas.py             Public DTOs (PayrollRunRequest, PayslipResult, …)
├── rules/
│   ├── loader.py              Loads YAML from business_rules/payroll/; caches; reloadable
│   ├── resolver.py            Layered override resolver (statutory→CCT→company→contract)
│   ├── plan.py                CalculationPlan: ordered list of PlanSteps
│   └── models.py              Internal rule-doc Pydantic models
├── primitives/                Deterministic primitives — all arithmetic lives here
│   ├── base.py                Primitive Protocol + registry
│   ├── irs.py                 IRS withholding (tabela de retenção na fonte)
│   ├── tsu.py                 TSU (Segurança Social) employer + employee
│   ├── subsidios.py           Subsídio de férias / Natal / alimentação
│   ├── overtime.py            Trabalho suplementar
│   ├── proration.py           Partial-period proration
│   └── rounding.py            Rounding & Decimal policy
├── engine/
│   ├── executor.py            Executes a CalculationPlan → PayslipResult
│   ├── time_input.py          Normalises time/attendance into payable items
│   └── audit.py               Builds the per-line audit trail + renders citations
├── ai/
│   ├── orchestrator.py        Anthropic SDK client; intent → tool calls → narration
│   ├── tools.py               Tool definitions wrapping PayrollService methods
│   └── prompts.py             System prompts (thin; rules loaded at runtime)
└── errors.py                  Typed exceptions
```

**Boundary rules:**
- UI imports only from `logic/payroll/public/`.
- DB is reached only through repository interfaces injected into `PayrollService`.
- Primitives know nothing about YAML or DBs.
- The AI module never imports primitives directly — it goes through `PayrollService`.

**Data flow for "run payroll for May 2026":**
1. UI sends natural-language intent to `ai/orchestrator.py`.
2. AI calls the `run_payroll` tool with `{period_id, scope}`.
3. `PayrollService.run_payroll(...)` resolves a `CalculationPlan` per in-scope employee and executes it.
4. Results return as `PayslipResult` objects with full audit trails.
5. AI narrates, citing clauses via `explain_line`.

## 5. Data Model (Read-Only Domain View)

These are the Pydantic v2 domain models the logic layer reads. Persistence shapes (DB schemas, ORM) are separate and deferred — repositories return these models.

### Identity & contract

- **`Employee`** — `employee_id`, `full_name`, `tax_id (NIF)`, `social_security_id (NISS)`, `birth_date`, `hire_date`, `status (active | suspended | terminated)`, `fiscal_profile`, `current_contract_id`, `bank_iban`.
- **`FiscalProfile`** — `irs_table_code` (one of the Portuguese tabelas: solteiro, casado-único-titular, casado-dois-titulares, etc.), `dependents`, `has_disability`, `spouse_has_disability`, `residency_status (resident | non_habitual_resident | non_resident)`, `voluntary_irs_rate` (optional override).
- **`Contract`** — `contract_id`, `employee_id`, `type (CT | CTT | CTI | part_time | internship)`, `start_date`, `end_date`, `role_category` (free-text + optional CCT-defined code), `weekly_hours`, `fte_percent`, `base_monthly_salary`, `cct_reference` (optional), `company_id`, `pay_frequency (monthly | biweekly | weekly)`.
- **`CompensationPackage`** — per-contract entitlements: list of `CompensationEntitlement {component_code, parameters}`. Drives which optional primitives apply (meal allowance, transport, fixed bonuses, diuturnidades amounts, etc.).

### Period & inputs

- **`PayrollPeriod`** — `period_id`, `company_id`, `pay_frequency`, `start_date`, `end_date`, `pay_date`, `status (open | calculated | closed)`.
- **`TimeInput`** — per (employee, period): `normal_hours`, `overtime_buckets {first_hour, additional_hours, weekend, holiday, night}`, `absences: list[AbsenceEntry]`, `meal_allowance_days`, `notes`.
- **`AbsenceEntry`** — `start_date`, `end_date`, `code` (justified illness, unjustified, parental, vacation taken, etc. — codes are YAML-driven so CCT-specific codes work), `paid_percent` (filled by the resolver from rules).

### Reference linkage

- **`CCTReference`** — `cct_id` (matches a YAML file in `business_rules/payroll/ccts/`), `cct_version`, `role_category_code`. Validation ensures the referenced doc exists and the category is defined within it.
- **`Company`** — `company_id`, `legal_name`, `tax_id`, `default_rounding_policy`, `default_subsidio_payment_mode (one_shot | duodecimos)`.

### Output

- **`PayslipResult`** — `period_id`, `employee_id`, `gross_earnings: list[PayslipLine]`, `deductions: list[PayslipLine]`, `employer_contributions: list[PayslipLine]`, `net_pay`, `audit: list[AuditTrailEntry]`.
- **`PayslipLine`** — `component_code`, `description`, `amount: Decimal`, `quantity?`, `rate?`, `tax_treatment (taxable | exempt | partially_exempt)`, `source_audit_ref` (FK into `audit`).
- **`AuditTrailEntry`** — `step_index`, `primitive`, `inputs_snapshot`, `output`, `rule_citation {document_path, layer, component_code, clause}`, `timestamp`.

### Decimal discipline

Every monetary field is `decimal.Decimal` with explicit context (28-digit precision, ROUND_HALF_UP default but overridable per company and per primitive). Floats are banned in the engine; YAML loaders reject float literals and parse numbers from quoted strings.

## 6. Rule Resolver & Layered Overrides

### Layer stack (lowest to highest priority)

1. **Statutory** — `business_rules/payroll/statutory_pt.yaml`. Portuguese baseline: IRS tables, TSU rates and bases, statutory subsídios (férias/Natal), overtime multipliers, minimum wage, default absence-pay percentages, hourly-rate derivation formula.
2. **CCT/IRCT** — `business_rules/payroll/ccts/<cct_id>.yaml`. Industry-specific overrides and additions referenced by `Contract.cct_reference.cct_id`. Can override statutory parameters (e.g., higher overtime multiplier, longer vacation), declare new components (e.g., subsídio de turno, diuturnidades schedule), and define role-category minimums.
3. **Company** — `business_rules/payroll/companies/<company_id>.yaml`. Company-wide policies on top of statutory/CCT: extra benefits, internal allowances, rounding policy, subsídio payment mode, pay-date offsets.
4. **Contract** — individual contract data (not YAML). Overrides at the row level only for explicitly-allowed fields. Fields marked `locked: true` in a lower layer reject overrides with `RuleViolation`.

### Merge semantics

- Components are keyed by `component_code`.
- Scalars are replaced by higher layers.
- Object fields are deep-merged.
- Arrays default to `replace`; a clause can opt into `append`.
- A layer can disable a lower-layer component with `disabled: true`.
- A layer can declare a new component absent from lower layers.
- Every merge produces a `RuleCitation { document_path, layer, component_code, clause }` recorded into the resulting plan step.

### Output: `CalculationPlan`

```python
CalculationPlan {
    employee_id, contract_id, period_id, company_id,
    rounding_policy,
    steps: list[PlanStep]
}

PlanStep {
    index,
    phase: input | gross | pre_tax_deduction | tax | post_tax | employer_contribution,
    component_code, primitive_name, parameters,
    inputs_required: list[str],   # component_codes this step depends on
    citations: list[RuleCitation],
}
```

**Phase execution order (fixed):**

1. `input` — synthetic steps that normalize raw `TimeInput` into payable items (worked-hours derivation, hourly-rate derivation, absence intersection with period). No monetary output by themselves.
2. `gross` — earnings primitives (`BaseSalary`, `Diuturnidades`, `OvertimeCalculator`, `MealAllowance`, `SubsidioFerias`, `SubsidioNatal`, `FixedAllowance`).
3. `pre_tax_deduction` — deductions that reduce the taxable base (e.g., absence deductions for unpaid leave, contributions to specific funds when applicable).
4. `tax` — `IRSWithholdingTable` and the employee-side `TSUContribution`. These read the `taxable_gross` accumulated from `gross` minus `pre_tax_deduction`.
5. `post_tax` — deductions applied after tax (garnishments-style mechanics if introduced later; v1 ships this phase empty but reserved).
6. `employer_contribution` — employer-side `TSUContribution` and any other employer-only obligations. Does not affect `net_pay`; appears on the payslip and on GL postings.

Within each phase, steps are topologically sorted by declared `inputs_required`. Across phases, ordering is fixed. The plan is serializable — persisting it alongside the payslip is what makes long-tail recomputation reproducible.

### Up-front validation

Before any execution, the resolver validates: all `inputs_required` resolvable in the plan, all primitives registered, all parameters match the primitive's `parameter_schema`, all citations populated. A plan that fails validation never executes — the AI surfaces the validation errors verbatim.

## 7. Compensation Primitives

### Primitive contract

```python
class Primitive(Protocol):
    name: str                              # registry key referenced by YAML
    parameter_schema: type[BaseModel]      # validates YAML parameters at plan-build
    input_schema: type[BaseModel]          # validates inputs at execution time
    output_schema: type[BaseModel]         # what execute() returns

    def execute(self, params, inputs, context: ExecutionContext) -> PrimitiveResult: ...
```

`PrimitiveResult` carries:
- `amount: Decimal`
- optional `quantity` / `rate` (for payslip display)
- `tax_treatment: taxable | exempt | partially_exempt` (with split amounts for partial)
- optional `breakdown` (sub-rows for transparency, e.g., overtime by bucket)
- `notes`

Primitives are pure functions of their declared inputs. They never read globals, never call DBs, never invoke the AI.

### v1 primitive inventory

**Earnings (phase: `gross`)**

| Primitive | Purpose |
|---|---|
| `BaseSalary` | Monthly base; auto-prorated by `Prorate` when contract straddles the period |
| `Diuturnidades` | Seniority bonus from a CCT-defined schedule `(years_served → amount)` |
| `OvertimeCalculator` | `hourly_base × hours × multiplier` per bucket; multipliers statutory-default, CCT-overridable |
| `MealAllowance` | `daily_rate × eligible_days`; output split into exempt/taxable per cash/card thresholds |
| `SubsidioFerias` | Vacation allowance; one-shot or duodécimos mode; applies accrual factor for partial-year |
| `SubsidioNatal` | Christmas allowance; same modes/accrual as férias |
| `FixedAllowance` | Generic per-period fixed amount (transport, function allowance, etc.); parametrized by amount, taxability, TSU base inclusion |
| `AbsenceDeduction` | Converts `TimeInput.absences` to deduction lines using `paid_percent` resolved per absence code |

**Taxes & contributions (phase: `tax` / `employer_contribution`)**

| Primitive | Purpose |
|---|---|
| `IRSWithholdingTable` | Selects tabela from `fiscal_profile`; looks up bracket for `taxable_gross`; tabela YAML versioned by `effective_from` |
| `TSUContribution` | `rate × sum(contribution_base components)`; used for both employee (11%) and employer (23.75%) as separate plan steps |

**Utility primitives (used by the executor, not authored in YAML)**

| Primitive | Purpose |
|---|---|
| `Prorate` | Proration factor `worked_days / period_days`; applied automatically when contract dates require it |
| `Rounding` | Wraps every primitive's output with the contract's `RoundingPolicy` |

### Registry & extension

`primitives/base.py` exposes a `@register("PrimitiveName")` decorator and a `PrimitiveRegistry` singleton. Adding a brand-new statutory mechanism: write a new Primitive class, register it, add a clause in a YAML doc. No engine changes.

## 8. Public Function Surface (`PayrollService`)

`PayrollService` is the **only** entry point into the logic layer. UI never imports anything else; the AI's tools wrap these same methods.

### Construction

```python
PayrollService(
    employee_repo: EmployeeRepository,
    contract_repo: ContractRepository,
    period_repo: PeriodRepository,
    time_input_repo: TimeInputRepository,
    payslip_repo: PayslipRepository,
    rule_loader: RuleLoader,
    primitive_registry: PrimitiveRegistry,
    clock: Clock = SystemClock(),
)
```

All return Pydantic DTOs and raise typed exceptions on rule violations.

### Registry — employees & contracts

- `create_employee(input: CreateEmployeeInput) → Employee`
- `update_employee(employee_id, patch: EmployeePatch) → Employee`
- `terminate_employee(employee_id, termination_date, reason) → Employee`
- `create_contract(input: CreateContractInput) → Contract`
- `update_contract(contract_id, patch: ContractPatch) → Contract` — rejects patches that touch `locked` fields or that fall inside a period already calculated against this contract.
- `get_employee(employee_id) → EmployeeWithContext` (employee + current contract + fiscal profile + compensation package)

### Period management

- `open_period(company_id, definition: PeriodDefinition) → PayrollPeriod`
- `get_period(period_id) → PayrollPeriod`
- `close_period(period_id) → PayrollPeriod` — transitions to `closed`; everything related becomes immutable. Fails if any employee in scope lacks a calculated payslip.

### Time & attendance ingestion

- `set_time_input(period_id, employee_id, input: TimeInputDraft) → TimeInput` — idempotent upsert; fails on closed periods.
- `register_absence(employee_id, entry: AbsenceEntryDraft) → AbsenceEntry` — independent of any specific period; the engine joins by date overlap.
- `get_time_input(period_id, employee_id) → TimeInput`

### Plan & calculation (the core)

- `build_calculation_plan(period_id, employee_id) → CalculationPlan` — pure resolution + validation; no execution, no writes.
- `dry_run_payslip(period_id, employee_id) → PayslipResult` — builds plan, executes, does **not** persist. Audit trail fully populated, transient.
- `run_payroll(period_id, scope: RunScope) → BatchRunResult` — `scope` is `all_active | list[employee_id]`. Two-phase execution:
  1. **Validation phase.** Build a `CalculationPlan` for every in-scope employee. If *any* employee fails plan build or input validation, the entire run aborts before execution. `BatchRunResult.status = aborted`, the period remains `open`, no payslips are written, and per-employee findings (`success | blocked_by_rule | blocked_by_missing_input`) are returned so the admin can fix the inputs or narrow `scope` and retry.
  2. **Execution phase.** Only reached if all validations pass. All `PayslipResult`s, audit trails, and the period status transition (`open → calculated`) commit in a single repository transaction. Either everything persists or nothing does. `BatchRunResult.status = succeeded` with aggregate totals.
- `recalculate_employee(period_id, employee_id, reason) → PayslipResult` — allowed on `calculated` periods (not `closed`); writes a new audit record citing the reason and the user.

### Read & explain

- `get_payslip(period_id, employee_id) → PayslipResult`
- `list_payslips(period_id, filter: PayslipFilter | None) → list[PayslipResult]`
- `get_audit_trail(period_id, employee_id) → list[AuditTrailEntry]`
- `explain_line(period_id, employee_id, line_id) → LineExplanation` — returns the line, its audit entries, and the verbatim YAML clauses cited. This is what the AI calls before narrating a number.

### Rule administration

- `reload_rules() → RuleStackSummary` — flushes the YAML cache and re-validates the full stack.
- `validate_rules(scope: RuleValidationScope) → list[RuleValidationIssue]` — schema + cross-layer consistency check; intended for CI.

### Cross-cutting guarantees

- **Atomicity.** `run_payroll` is one transaction at the repository layer (period status + all payslips + audit trails commit together).
- **Idempotency.** Rerunning `run_payroll` on a `calculated` period replaces prior results, appending an audit record naming the previous results (never deletes audit history).
- **Immutability.** `closed` periods reject every write.
- **Determinism.** Plan + inputs + same YAML stack → identical numbers, always. `RuleStackSnapshot` is captured once per `build_calculation_plan` and frozen for that plan's lifetime.
- **Concurrency.** Repository-level advisory lock on `(period_id)` for `run_payroll`; second call fails with `PeriodInProgress`.

## 9. AI Orchestration & Audit Trail

### Client & model

`ai/orchestrator.py` uses the Anthropic SDK with `claude-sonnet-4-6`. Each turn opens a tool-use loop until the model produces a final text response.

### Prompt strategy

The system prompt is small (~600 tokens) and rule-free. It says: *you orchestrate Portuguese payroll operations; you never produce monetary numbers yourself; for any number you describe, you MUST have received it from a tool result; for any explanation, you MUST call `explain_line` to obtain the verbatim citation*.

The **rule stack snapshot** (resolved YAML for the active company at the requested period date) is appended as a separate cacheable context block — typically 5–30 KB. Both the system prompt and the rule snapshot use Anthropic's `cache_control: ephemeral` markers; the rule stack stays warm across turns and across employees within the same run.

### Tool surface (1:1 with `PayrollService`)

- `list_active_employees(filter)`, `get_employee_with_context(employee_id)`
- `get_period(period_id)`, `open_period(...)`, `close_period(...)`
- `set_time_input(...)`, `register_absence(...)`, `get_time_input(...)`
- `build_calculation_plan(period_id, employee_id)`
- `dry_run_payslip(period_id, employee_id)`
- `run_payroll(period_id, scope)` — UI is expected to gate with explicit confirmation
- `get_payslip(...)`, `list_payslips(...)`, `get_audit_trail(...)`
- `explain_line(period_id, employee_id, line_id)`

Each tool has a strict JSON schema. The orchestrator validates arguments against `PayrollService` input models before invocation. Tool errors are typed (`MissingInput`, `RuleViolation`, `ImmutablePeriod`, `RuleValidationError`); the AI surfaces them verbatim, not paraphrased.

### Audit trail flow

`Primitive.execute()` → `PrimitiveResult` carries `citations: list[RuleCitation]` (originating clauses for parameters used).
↓
`engine/executor` wraps each result in an `AuditTrailEntry { step_index, primitive, inputs_snapshot, output, rule_citation, timestamp }` and attaches it to the `PayslipResult`. Every `PayslipLine` has a `source_audit_ref` pointing to its entry.
↓
`engine/audit.py` renders an audit entry into a human-readable string with the verbatim YAML clause text fetched by the `RuleLoader`. This is what `explain_line` returns — the AI does not have to interpret YAML structure; it gets prose-ready citation text.

### Citation guarantees

- Numbers in narration must come from tool results — enforced at testing time via a narration validator (regex pass over the model's final text against amounts returned by the most recent tool calls).
- `explain_line` returns a `citation_text` field that is the verbatim YAML snippet plus document path and version.
- The system prompt forbids producing explanations without first calling `explain_line` for the relevant line(s).

Every monetary value the user sees has a traceable path from `clause in YAML` → `RuleCitation` → `AuditTrailEntry` → `PayslipLine` → AI narration.

## 10. Validation, Errors, and Edge Cases

### Three validation layers

1. **Load-time** (`RuleLoader`): schema validation per layer, version/effective-date sanity, file existence for referenced CCTs. Float literals rejected; numeric strings only, parsed into `Decimal`.
2. **Plan-build time** (`build_calculation_plan`): cross-layer consistency, primitive registration, parameter schema validation, dependency DAG check.
3. **Execution time** (`engine/executor`): required inputs present, `Decimal` sign checks, `Prorate` factor in `[0, 1]`. Failures here are bugs and raise `EngineInvariantError`.

### Typed exceptions (`logic/payroll/errors.py`)

| Exception | Trigger |
|---|---|
| `RuleLoadError` | Bad YAML, schema mismatch, missing file |
| `RuleValidationError` | Cross-layer issues from `validate_rules` or plan build |
| `MissingInput` | Required input absent (e.g., no fiscal profile, no time input) |
| `RuleViolation` | Operation rejected by an active rule (e.g., editing a `locked` field, mid-period contract change) |
| `ImmutablePeriod` | Write attempt on a `closed` period |
| `PeriodInProgress` | Concurrent `run_payroll` attempt |
| `EngineInvariantError` | Internal bug; surfaces with full plan + inputs for post-mortem |

Every exception carries a stable `code`, human messages in Portuguese (primary) and English (fallback), and where applicable a `citation` pointing to the rule that triggered it. The AI surfaces them verbatim.

### Edge cases & handling

| Case | Behavior |
|---|---|
| Mid-period contract change | `update_contract` rejects effective dates inside an open period with `RuleViolation { code: MID_PERIOD_CONTRACT_CHANGE }`. Off-cycle handling deferred to follow-up spec. |
| Hire / termination mid-period | `Prorate` produces a factor; subsídios apply accrual factors based on reference-year time worked. |
| Negative net pay | Payslip produced with `net_pay < 0` plus a `NegativeNetPayWarning` on the audit trail; period transitions to `calculated`; `BatchRunResult` flags the employee for human review. AI required to surface the warning. |
| Parental leave / SS-paid absences | Absence codes carry `salary_replacement: employer | social_security | unpaid`. Resolver routes employer-side components to zero with an audit line citing the absence code clause. Complex multi-party reconciliation off-cycle. |
| Multiple absences on the same day | `register_absence` rejects overlaps in v1 (`RuleViolation { code: OVERLAPPING_ABSENCE }`). Half-day codes deferred. |
| Subsídio with no accrual | Primitive returns `amount = 0` with audit "no entitlement accrued for period." |
| Absence overlapping period boundary | Engine intersects with the period and contributes only the in-period portion. |
| Hourly rate derivation for overtime | `monthly_salary × 12 / (52 × weekly_hours)`, declared as a statutory YAML clause and read by `OvertimeCalculator`. |
| Rule reload mid-run | `RuleStackSnapshot` captured at plan-build and frozen; concurrent reloads do not affect in-flight calculations. |
| Concurrent `run_payroll` | Advisory lock on `(period_id)`; second call fails with `PeriodInProgress`. |
| Unknown absence code | `register_absence` rejects with a list of valid codes from the active rule stack. |

## 11. Testing Strategy

### Layout

```
tests/payroll/
├── primitives/        one file per primitive
├── rules/             loader, resolver (layer merging + citations), plan builder
├── engine/            executor, audit-trail rendering
├── service/           PayrollService methods with in-memory repos
├── golden/            input fixture → expected payslip JSON, one per scenario
├── ai/                orchestrator with mocked Anthropic client + narration validator
└── conftest.py        shared fixtures (in-memory repos, test rule stack, test clock)
```

### Tooling

- `pytest` + `pytest-asyncio` (per CLAUDE.md)
- `hypothesis` for property-based invariants
- `syrupy` for payslip snapshots
- A hand-rolled `FakeAnthropicClient` for AI tests; no live API calls
- All `Decimal` comparisons use `==` with explicit precision; no `pytest.approx`

### Primitive tests

One file per primitive. Each covers nominal case, boundary cases (zero, exempt threshold, bracket edges), rounding policy variations, invalid-input rejection. **Target: 100% line + branch coverage.**

### Resolver tests

Explicit tests per documented semantic: deep-merge on scalars, replace-vs-append on arrays, `disabled: true` propagation, `locked` field protection, missing-clause fallthrough. Every test asserts both the resolved value AND the citation chain.

### Engine integration tests

End-to-end `build_calculation_plan → execute → PayslipResult` against synthetic inputs with a minimal rule stack. Asserts plan topology, phase ordering, audit completeness.

### Service tests

`PayrollService` against in-memory repository fakes. Covers idempotency of `set_time_input`, immutability of `closed` periods, the two-phase semantics of `run_payroll` (validation-phase abort leaves the period and prior payslips unchanged; execution-phase commit is all-or-nothing), `recalculate_employee` writing audit reasons, concurrent-run rejection.

### Golden-file tests

One scenario per file, each a triplet `{rule_stack.yaml, inputs.yaml, expected_payslip.json}`. Pytest parametrizes over the directory. Minimum scenarios:

- Salaried monthly full-time, clean month
- Salaried monthly with duodécimos subsídios
- Hourly with overtime across all buckets
- Mid-month hire (proration)
- Mid-month termination (proration + subsídio accrual)
- IRS tabela variations: solteiro / casado-único / casado-dois / with dependents
- CCT overrides: overtime multiplier, diuturnidades, additional vacation
- Partial month with justified absence
- Parental leave absence (SS-paid)
- Negative-net-pay warning case

Golden files are reviewed before commit and become the regression contract.

### Property-based invariants (`hypothesis`)

- **Determinism.** Same inputs + same rule stack → byte-identical payslip JSON.
- **Audit completeness.** Every `PayslipLine.source_audit_ref` resolves to an `AuditTrailEntry`.
- **Citation completeness.** Every `AuditTrailEntry.rule_citation` references a document path + clause that exists in the resolved stack.
- **Layer precedence.** Random layer stacks with conflicting clauses → higher layer wins for non-`append` fields.
- **Sign discipline.** Gross earnings ≥ 0, deductions ≥ 0, employer contributions ≥ 0. Net pay can be negative; nothing else.

### AI orchestrator tests

Mocked SDK; structural assertions only:
- Given an intent transcript, the orchestrator emits the expected sequence of tool calls (snapshot test).
- The narration validator rejects any final-message text containing numbers not present in the most recent tool result(s).
- `explain_line` returns the verbatim YAML snippet for cited clauses.

We never assert on Claude's prose — only on structured tool-use behavior and on the deterministic narration validator.

### CI rule validation

`validate_rules` runs in CI against the shipped YAML stack. A breaking change in `statutory_pt.yaml` fails the build, forcing migration notes.

### Coverage targets

| Layer | Target |
|---|---|
| Primitives | 100% line + branch |
| Resolver / engine | ≥ 95% |
| Service | ≥ 90% |
| AI | Structural only (no percentage target) |

## 12. Glossary

| Term | Meaning |
|---|---|
| CT | Contrato de Trabalho sem termo — open-ended employment contract |
| CTT | Contrato de Trabalho a Termo Certo — fixed-term contract |
| CTI | Contrato de Trabalho a Termo Incerto — uncertain-term contract |
| CCT / IRCT | Contrato Coletivo de Trabalho / Instrumento de Regulamentação Coletiva de Trabalho — industry collective bargaining agreement |
| IRS | Imposto sobre o Rendimento das Pessoas Singulares — personal income tax |
| Tabela de retenção na fonte | IRS withholding table; selected per fiscal profile |
| TSU | Taxa Social Única — social security contribution (11% employee, 23.75% employer baseline) |
| Subsídio de férias | Vacation allowance, ~1 month's salary annually |
| Subsídio de Natal | Christmas allowance, ~1 month's salary annually |
| Subsídio de alimentação | Meal allowance, with daily tax-exempt threshold (cash vs card) |
| Duodécimos | Subsídio paid in 1/12 monthly fractions rather than one-shot |
| Diuturnidades | Seniority bonus typically defined by CCT |
| Trabalho suplementar | Overtime work |
| Segurança Social | Portuguese social security |
| NIF | Número de Identificação Fiscal — tax ID |
| NISS | Número de Identificação de Segurança Social — social security ID |
