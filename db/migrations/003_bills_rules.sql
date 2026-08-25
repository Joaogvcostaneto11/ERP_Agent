-- Versioned storage for the bills purchase-invoice rule document.
--
-- WHERE THIS LIVES, AND WHY IT MATTERS
-- Run this against the database BILLS_WRITE_DATABASE_URL points at, for the
-- same reason as 002: the rule document decides which columns a write lands in,
-- so it belongs beside the rows it governs rather than in a second database
-- that could drift from them.
--
-- WHY THE DATABASE AND NOT THE REPO
-- The document used to live at business_rules/bills/purchase_invoice.yaml and
-- was rewritten in place by the admin panel. On Render the container filesystem
-- is ephemeral: every deploy and every restart silently reverted an operator's
-- mapping change back to whatever was baked into the image, and the JSONL that
-- recorded the change went with it. The packaged YAML is now a SEED only --
-- it populates this table once, on first use of an empty table, and is never
-- written to again.
--
-- ONE TABLE, NOT TWO
-- Each row is one version of the document AND the record of who changed it,
-- why, and to what. Keeping provenance in the same INSERT as the content is
-- what stops the two from ever disagreeing.
--
-- Version is the primary key, which is load-bearing rather than decorative:
-- two admins applying a change against the same base version collide on the
-- INSERT instead of one silently overwriting the other's work.
--
-- Ts is NVARCHAR for the same reason as 002: AuditLog.now_iso() already emits
-- a sortable ISO-8601 UTC string, and storing it verbatim keeps this column
-- identical to the JSONL mirror's value.
--
-- Re-running this script is harmless.

IF OBJECT_ID('dbo.ERPAgent_BillRules', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ERPAgent_BillRules (
        Version     INT            NOT NULL PRIMARY KEY,
        Yaml        NVARCHAR(MAX)  NOT NULL,
        Ts          NVARCHAR(32)   NOT NULL,
        -- 'seed' rows have no operator: nobody made that change, it is the
        -- document the image shipped with.
        Action      NVARCHAR(16)   NOT NULL,   -- 'seed' | 'apply' | 'revert'
        Operator    NVARCHAR(128)  NULL,
        -- The admin's own words. `Rationale` is Claude's paraphrase and cannot
        -- stand in for them, so both are kept.
        Prose       NVARCHAR(MAX)  NULL,
        Rationale   NVARCHAR(MAX)  NULL,
        Changes     NVARCHAR(MAX)  NULL,       -- JSON array of FieldChange
        RevertedTo  INT            NULL        -- set only when Action = 'revert'
    );
END
GO
