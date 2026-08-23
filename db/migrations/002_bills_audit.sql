-- Audit trail for bill ingestion writes.
--
-- WHERE THIS LIVES, AND WHY IT MATTERS
-- The row is inserted inside the same transaction as the document it records,
-- so it must sit in the same database as the documents. The application writes
-- through BILLS_TABLE_PREFIX (default "ForumSI.dbo."), so the connection's
-- default database is NOT where this belongs -- BILLS_WRITE_DATABASE_URL points
-- at DevDB while Doc001 and friends live in ForumSI. Creating the table in the
-- connection's default database would leave every audit INSERT failing on a
-- missing object, and because the insert deliberately does not swallow, every
-- commit would roll back.
--
-- If BILLS_TABLE_PREFIX is overridden, change the USE below to match it.
--
-- Payload holds the whole audit entry as JSON, so adding a field later needs no
-- migration; the promoted columns exist only to make the common queries cheap.
--
-- Ts is NVARCHAR rather than DATETIME2 on purpose: AuditLog.now_iso() already
-- produces a sortable ISO-8601 UTC string, and storing it verbatim keeps this
-- column identical to the JSONL mirror's value with no driver-dependent
-- conversion in between.
--
-- Re-running this script is harmless.

USE ForumSI;
GO

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
GO
