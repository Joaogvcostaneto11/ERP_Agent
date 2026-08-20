-- Audit trail for bill ingestion writes.
--
-- Lives in the database reached by BILLS_WRITE_DATABASE_URL, not somewhere
-- tidier, because the row is inserted inside the same transaction as the
-- document it records: either both land or neither.
--
-- Payload holds the whole audit entry as JSON, so adding a field later needs no
-- migration; the promoted columns exist only to make the common queries cheap.
--
-- Ts is NVARCHAR rather than DATETIME2 on purpose: AuditLog.now_iso() already
-- produces a sortable ISO-8601 UTC string, and storing it verbatim keeps this
-- column identical to the JSONL mirror's value with no driver-dependent
-- conversion in between.
IF OBJECT_ID('dbo.ERPAgent_BillAudit', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ERPAgent_BillAudit (
        Id            BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Ts            NVARCHAR(32)   NOT NULL,
        Operator      NVARCHAR(128)  NOT NULL,
        ProposalId    NVARCHAR(64)   NOT NULL,
        Status        NVARCHAR(16)   NOT NULL,
        DocumentChave INT            NULL,
        SupplierChave INT            NULL,
        RuleDoc       NVARCHAR(128)  NULL,
        RuleVersion   NVARCHAR(32)   NULL,
        Payload       NVARCHAR(MAX)  NOT NULL
    );
    CREATE INDEX IX_ERPAgent_BillAudit_Ts ON dbo.ERPAgent_BillAudit (Ts DESC);
    CREATE INDEX IX_ERPAgent_BillAudit_Doc ON dbo.ERPAgent_BillAudit (DocumentChave);
END
