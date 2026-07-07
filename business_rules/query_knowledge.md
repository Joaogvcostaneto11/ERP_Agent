# Query Knowledge — Business rules for interpreting questions

Authoritative business rules for translating user questions into SQL. Prefer them over inference. Note the KE id you applied in your citation.

### KE-0001 — Untitled
d
- **Provenance:** added 2026-06-22 · source turn

### KE-0002 — Untitled
I need to see the developer's explanation to write the knowledge entry, but it appears to be empty in the message. Could you please provide the developer's explanation of what the correct rule/approach should be?
- **Provenance:** added 2026-06-22 · source turn

### KE-0003 — Sales Analytics Using Document Type Groups (GrpDoc) with Sign Correction
- **Intent:** Questions asking for sales totals, invoice amounts, or revenue figures filtered by a named document group (e.g. "Análise de Vendas"), where the sign of the document type must be applied correctly to produce meaningful financial values.
- **Business rule:** Documents (Doc001) have types (TiposDoc), and document types belong to one or more named groups (GrpDoc) via the bridge table GrpDocTp. To aggregate sales correctly: (1) join GrpDoc → GrpDocTp → TiposDoc → Doc001; (2) the net amount is `(Iliquido - DescontoTotal)`, where `Iliquido` is the gross amount and `DescontoTotal` is the total discount; (3) each document type has a `Sinal` column (0 = negative/credit, 1 = positive/debit) — multiply the net amount by `(Sinal - 1)` to apply the correct sign (positive documents yield 0 × net = 0 when Sinal=1, but the pattern `(Sinal - 1)` as used here means Sinal=0 gives -1 and Sinal=1 gives 0; confirm the intended direction with the developer). The same sign factor applies to IVA. GrpDocTp links groups to document types with the group as FK (`CF`) and the document type as PK (`CP`).
- **Schema mapping:**
  - `GrpDoc.Chave` / `GrpDoc.Nome` — named document group (e.g. `'Analise de Vendas'`)
  - `GrpDocTp.CF` → `GrpDoc.Chave` (group FK)
  - `GrpDocTp.CP` → `TiposDoc.Chave` (document type FK)
  - `TiposDoc.Sinal` — sign of the document type (0 = negative, 1 = positive)
  - `Doc001.TipoDoc` → `TiposDoc.Chave`
  - `Doc001.Iliquido` — gross amount before discount
  - `Doc001.DescontoTotal` — total discount amount
  - `Doc001.IVA` — VAT amount
  - Date filter: `YEAR(d.Data) = <year>`
- **Example query:** `SELECT COUNT(DISTINCT d.Chave) AS NumDocs, SUM((d.Iliquido - d.DescontoTotal) * (t.Sinal - 1)) AS Liquido, SUM(d.IVA * (t.Sinal - 1)) AS TotalIVA FROM GrpDoc g JOIN GrpDocTp gt ON g.Chave = gt.CF JOIN TiposDoc t ON t.Chave = gt.CP JOIN Doc001 d ON t.Chave = d.TipoDoc WHERE g.Nome = 'Analise de Vendas' AND YEAR(d.Data) = 2026`
- **Scope:** DevDB, ForumSI
- **Provenance:** added 2026-06-22 · source turn

### KE-0004 — Sales Calculation: Sum Line Values Using TiposDoc.Sinal for Sign Correction
- **Intent:** Questions asking for total sales, revenue, or invoice amounts — especially when aggregating across document types (invoices, credit notes, etc.) using a document group like 'Analise de Vendas'.
- **Business rule:** To calculate net sales value from document lines, multiply each line's `Valor` by the document type's `Sinal` (sign indicator from `TiposDoc`). The correct formula is `SUM(l.Valor * t.Sinal)` — not `SUM(l.Valor * (t.Sinal - 1))`. Lines must be joined to their article (`Artigos`) via `LinDoc001.ChaveProd = Artigos.Chave`, filtering out non-article lines with `l.ChaveProd <> 0`. The document group 'Analise de Vendas' in `GrpDoc` defines which document types count as sales.
- **Schema mapping:**
  - `GrpDoc.Nome = 'Analise de Vendas'` — identifies the sales document group
  - `GrpDoc.Chave` → `GrpDocTp.CF` — links group to its document types
  - `GrpDocTp.CP` → `TiposDoc.Chave` — resolves each document type
  - `TiposDoc.Sinal` — sign multiplier (+1 for sales, -1 for returns/credit notes)
  - `Doc001.TipoDoc` → `TiposDoc.Chave` — document header to type
  - `LinDoc001.Documento` → `Doc001.Chave` — lines to header
  - `LinDoc001.ChaveProd` → `Artigos.Chave` — lines to articles (filter `<> 0` to exclude text/subtotal lines)
  - `LinDoc001.Valor` — line total value (quantity × unit price after discount)
- **Example query:** `SELECT COUNT(DISTINCT l.Documento) AS NumDocs, SUM(l.Valor * t.Sinal) AS Liquido FROM GrpDoc g JOIN GrpDocTp gt ON g.Chave = gt.CF JOIN TiposDoc t ON t.Chave = gt.CP JOIN Doc001 d ON t.Chave = d.TipoDoc JOIN Entidades e ON e.Chave = d.Entidade JOIN LinDoc001 l ON d.Chave = l.Documento JOIN Artigos a ON a.Chave = l.ChaveProd WHERE g.Nome = 'Analise de Vendas' AND YEAR(d.Data) = 2026 AND l.ChaveProd <> 0`
- **Scope:** DevDB, ForumSI
- **Provenance:** added 2026-06-22 · source turn

### KE-0005 — Sales by Article — Correct Aggregation Without Sign Adjustment
- **Intent:** Questions asking for sales totals, revenue, or quantity per article (e.g. "order by article", "sales by article", "top articles")
- **Business rule:** When summing sales line values for a straightforward sales report, use `SUM(l.Valor)` directly. Do **not** apply a sign adjustment via `TiposDoc.Sinal` (e.g. `Valor * (Sinal - 1)`). The `Sinal` column is used for stock/accounting movement direction, not for sales revenue reporting. Filtering to the correct document types (invoices) via a sales group like `GrpDoc.Nome = 'Analise de Vendas'` or `TiposDoc` with positive sales intent is sufficient — the line `Valor` already carries the correct positive amount for sales lines.
- **Schema mapping:** `LinDoc001.Valor` — line total (already positive for sales); `TiposDoc.Sinal` — should NOT be used to transform `Valor` in revenue aggregations; filter sales documents via `Doc001.TipoDoc` joined to `TiposDoc`, or via `GrpDoc`/`GrpDocTp` group; `LinDoc001.ChaveProd <> 0` — excludes text/subtotal lines
- **Example query:** `SELECT a.Codigo, a.Nome AS Artigo, COUNT(DISTINCT d.Chave) AS NumDocs, SUM(l.Quantidade) AS Quantidade, SUM(l.Valor) AS Liquido FROM ForumSI.dbo.GrpDoc g JOIN ForumSI.dbo.GrpDocTp gt ON g.Chave = gt.CF JOIN ForumSI.dbo.TiposDoc t ON t.Chave = gt.CP JOIN ForumSI.dbo.Doc001 d ON t.Chave = d.TipoDoc JOIN ForumSI.dbo.LinDoc001 l ON d.Chave = l.Documento JOIN ForumSI.dbo.Artigos a ON a.Chave = l.ChaveProd WHERE g.Nome = 'Analise de Vendas' AND YEAR(d.Data) = 2026 AND l.ChaveProd <> 0 GROUP BY a.Codigo, a.Nome ORDER BY Liquido DESC`
- **Scope:** ForumSI, DevDB
- **Provenance:** added 2026-06-22 · source turn 
