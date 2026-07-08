-- ERP Agent: initial schema for Azure SQL / SQL Server
-- Run once against a fresh database.
-- All NVARCHAR columns ensure Unicode support for multi-language names.

CREATE TABLE employees (
    employee_id          NVARCHAR(50)   NOT NULL PRIMARY KEY,
    full_name            NVARCHAR(200)  NOT NULL,
    tax_id               NVARCHAR(20)   NOT NULL,
    social_security_id   NVARCHAR(20)   NOT NULL,
    birth_date           DATE           NOT NULL,
    hire_date            DATE           NOT NULL,
    status               NVARCHAR(20)   NOT NULL,
    fiscal_profile       NVARCHAR(MAX)  NOT NULL,  -- JSON: FiscalProfile
    current_contract_id  NVARCHAR(50)   NULL,
    bank_iban            NVARCHAR(34)   NULL
);

CREATE TABLE contracts (
    contract_id          NVARCHAR(50)    NOT NULL PRIMARY KEY,
    employee_id          NVARCHAR(50)    NOT NULL,
    type                 NVARCHAR(20)    NOT NULL,
    start_date           DATE            NOT NULL,
    end_date             DATE            NULL,
    role_category        NVARCHAR(100)   NOT NULL,
    weekly_hours         NUMERIC(8, 2)   NOT NULL,
    fte_percent          NUMERIC(5, 4)   NOT NULL,
    base_monthly_salary  NUMERIC(15, 2)  NOT NULL,
    cct_reference        NVARCHAR(MAX)   NULL,     -- JSON: CCTReference
    company_id           NVARCHAR(50)    NOT NULL,
    pay_frequency        NVARCHAR(20)    NOT NULL,
    CONSTRAINT fk_contracts_employee FOREIGN KEY (employee_id)
        REFERENCES employees (employee_id)
);

CREATE INDEX ix_contracts_employee_id ON contracts (employee_id);

CREATE TABLE payroll_periods (
    period_id    NVARCHAR(50)  NOT NULL PRIMARY KEY,
    company_id   NVARCHAR(50)  NOT NULL,
    pay_frequency NVARCHAR(20) NOT NULL,
    start_date   DATE          NOT NULL,
    end_date     DATE          NOT NULL,
    pay_date     DATE          NOT NULL,
    status       NVARCHAR(20)  NOT NULL
);

CREATE TABLE time_inputs (
    period_id           NVARCHAR(50)   NOT NULL,
    employee_id         NVARCHAR(50)   NOT NULL,
    normal_hours        NUMERIC(8, 2)  NOT NULL,
    overtime_buckets    NVARCHAR(MAX)  NOT NULL,  -- JSON: OvertimeBuckets
    absences            NVARCHAR(MAX)  NOT NULL,  -- JSON: list[AbsenceEntry]
    meal_allowance_days INT            NOT NULL DEFAULT 0,
    notes               NVARCHAR(MAX)  NOT NULL DEFAULT '',
    CONSTRAINT pk_time_inputs PRIMARY KEY (period_id, employee_id),
    CONSTRAINT fk_time_inputs_period   FOREIGN KEY (period_id)   REFERENCES payroll_periods (period_id),
    CONSTRAINT fk_time_inputs_employee FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
);

CREATE TABLE payslips (
    period_id              NVARCHAR(50)   NOT NULL,
    employee_id            NVARCHAR(50)   NOT NULL,
    gross_earnings         NVARCHAR(MAX)  NOT NULL,  -- JSON: list[PayslipLine]
    deductions             NVARCHAR(MAX)  NOT NULL,  -- JSON: list[PayslipLine]
    employer_contributions NVARCHAR(MAX)  NOT NULL,  -- JSON: list[PayslipLine]
    net_pay                NUMERIC(15, 2) NOT NULL,
    audit                  NVARCHAR(MAX)  NOT NULL,  -- JSON: list[AuditTrailEntry]
    CONSTRAINT pk_payslips PRIMARY KEY (period_id, employee_id),
    CONSTRAINT fk_payslips_period   FOREIGN KEY (period_id)   REFERENCES payroll_periods (period_id),
    CONSTRAINT fk_payslips_employee FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
);
