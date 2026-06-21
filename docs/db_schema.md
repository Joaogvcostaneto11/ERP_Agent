# Database Schema Reference — ForumSI / dbSoft ERP

Generated from live SQL Server 2025 at `149.86.232.229:1033`.
No FK constraints are defined in the DB — all relationships are **logical** (enforced by application).

## Databases

| Database | Tables | Views | Purpose |
|---|---|---|---|
| DevDB | 228 | 12 | ForumSI IT company — software sales, hardware, support |
| DOClinic | 190 | 49 | Medical clinic — consultations, exams, healthcare |
| DevCare | 190 | 49 | Mirror of DOClinic (same schema, same data volume) |
| ForumSI | 241 | 12 | Mirror of DevDB (same schema, same data volume) |
| OpenInnovation | 165 | 10 | Innovation entity — minimal data |

## Core Document Model (all databases share this structure)

### Doc001 — Document Headers
Primary source of commercial transactions (invoices, orders, quotes, etc.).

```
  Chave                                    bigint(19,0)           PK
  Codigo                                   varchar(20)           
  DC                                       smalldatetime         
  OC                                       bigint(19,0)          
  DUA                                      smalldatetime         
  OUA                                      bigint(19,0)          
  Hist                                     tinyint(3,0)          
  Data                                     smalldatetime         
  Estado                                   tinyint(3,0)          
  TipoDoc                                  bigint(19,0)          
  Entidade                                 bigint(19,0)          
  Operario                                 bigint(19,0)          
  Operador                                 bigint(19,0)          
  Armazem                                  bigint(19,0)          
  Posto                                    bigint(19,0)          
  Iliquido                                 decimal(19,2)         
  DescontoTotal                            decimal(19,2)         
  Outros                                   decimal(19,2)         
  Taras                                    decimal(19,2)         
  IVA                                      decimal(19,2)         
  Total                                    decimal(19,2)         
  RegIVA                                   bigint(19,0)          
  Moeda                                    bigint(19,0)          
  CondPag                                  bigint(19,0)          
  ModoPag                                  bigint(19,0)          
  Vendedor                                 bigint(19,0)          
  Desconto                                 decimal(9,2)          
  Cambio                                   decimal(9,2)          
  Vencimento                               smalldatetime         
  PrazoEnt                                 varchar(20)           
  Parcial                                  tinyint(3,0)          
  Expedicao                                varchar(75)           
  LocalM                                   varchar(75)           
  LocalL                                   varchar(75)           
  LocalCP                                  varchar(75)           
  LocalDesc                                varchar(100)           NULL
  HoraCarga                                smalldatetime         
  HoraDesc                                 smalldatetime         
  Lingua                                   bigint(19,0)          
  Volumes                                  bigint(19,0)          
  Obs                                      varchar(350)          
  DocCCO                                   bigint(19,0)          
  LocalCarga                               varchar(100)           NULL
  GrpFin                                   bigint(19,0)          
  GrpFac                                   bigint(19,0)          
  GrpCom                                   bigint(19,0)          
  VRef                                     varchar(20)           
  Psion                                    varchar(10)           
  Zona                                     bigint(19,0)          
  Classif                                  bigint(19,0)          
  Codpai                                   bigint(19,0)          
  chDocAuto                                bigint(19,0)          
  Serie                                    bigint(19,0)          
  Diferencas                               decimal(19,2)         
  Portes                                   decimal(19,2)         
  Autoriza                                 tinyint(3,0)          
  Anexos                                   smallint(5,0)         
  Etiqueta                                 tinyint(3,0)          
  Comissao                                 decimal(19,2)         
  Mercado                                  bigint(19,0)          
  ChComp                                   bigint(19,0)          
  Rota                                     bigint(19,0)          
  Prioridade                               tinyint(3,0)          
  Volume                                   varchar(2)            
  Lock                                     tinyint(3,0)          
  ValDesconto                              decimal(19,2)         
  Exportado                                tinyint(3,0)          
  Texto                                    varchar(200)          
  Cartao                                   bigint(19,0)          
  PontosAtribuidos                         smallint(5,0)         
  Contacto                                 varchar(75)           
  Horario                                  smalldatetime         
  IOStatus                                 smallint(5,0)         
  Seguro                                   smallint(5,0)         
  DocFile                                  varchar(100)          
  Certificacao                             varchar(250)          
  CertificacaoOriginal                     varchar(250)          
  CertificacaoEstado                       tinyint(3,0)          
  ATCUD                                    varchar(20)            NULL
  CodigoAT                                 varchar(50)            NULL
```

**Key columns:**
- `Chave` — surrogate PK (bigint), referenced by LinDoc001.Documento
- `Codigo` — human-readable document number (e.g. FA 2026/001)
- `TipoDoc` → TipoDoc.Chave — document type (1=Invoice, 2=Quote, ...)
- `Entidade` → Entidades.Chave — customer/supplier
- `Serie` → Series.Chave — numbering series
- `Data` — document date (filter for year: `Data >= '2026-01-01'`)
- `Vencimento` — due date
- `Estado` — status (0=draft, 1=active, ...)
- `Total` — document total (sum for sales analytics)
- `IVA` — VAT amount
- `Iliquido` — gross before discounts
- `Desconto` / `DescontoTotal` — discount
- `Operador` → Operadores/SYS — user who created it
- `Vendedor` → Vendedores — salesperson
- `Armazem` → Armazens — warehouse
- `Moeda` → Moedas — currency
- `ATCUD` / `CodigoAT` — Portuguese fiscal certification (AT authority)

### LinDoc001 — Document Lines
One row per line item within a Doc001 document.

```
  Chave                                    bigint(19,0)           PK
  DC                                       smalldatetime         
  OC                                       bigint(19,0)          
  DUA                                      smalldatetime         
  OUA                                      bigint(19,0)          
  Quantidade                               decimal(19,3)         
  ChaveProd                                bigint(19,0)          
  Documento                                bigint(19,0)          
  PCusto                                   decimal(19,5)         
  PVenda                                   decimal(19,5)         
  TpLinha                                  bigint(19,0)          
  Armazem                                  bigint(19,0)          
  Desconto                                 varchar(10)           
  Iva                                      decimal(9,2)          
  Descricao                                varchar(150)          
  Punit                                    decimal(19,5)         
  Obras                                    bigint(19,0)          
  LinAssoc                                 bigint(19,0)          
  QtEmb                                    bigint(19,0)          
  Valor                                    decimal(19,5)         
  QuantOrc                                 decimal(19,3)         
  QuantEnc                                 decimal(19,3)         
  QuantRes                                 decimal(19,3)         
  QuantProc                                decimal(19,3)         
  QuantSt                                  decimal(19,3)         
  QuantFact                                decimal(19,3)         
  QuantTransp                              decimal(19,3)         
  QuantDev                                 decimal(19,3)         
  QuantCred                                decimal(19,3)         
  QuantOrcP                                decimal(19,3)         
  QuantEncP                                decimal(19,3)         
  QuantResP                                decimal(19,3)         
  QuantProcP                               decimal(19,3)         
  QuantStP                                 decimal(19,3)         
  QuantFactP                               decimal(19,3)         
  QuantTranspP                             decimal(19,3)         
  QuantDevP                                decimal(19,3)         
  QuantCredP                               decimal(19,3)         
  DescL                                    decimal(19,5)         
  PCMedio                                  decimal(19,5)         
  Chpai                                    bigint(19,0)          
  chLinAuto                                bigint(19,0)          
  Encargos                                 decimal(19,5)         
  TaxaComissao                             decimal(19,5)         
  Autoriza                                 smallint(5,0)         
  Anexos                                   smallint(5,0)         
  Obs                                      varchar(50)           
  Plano                                    bigint(19,0)          
  Unidade                                  bigint(19,0)          
  FactorConvQt                             decimal(19,5)         
  FactorConvValor                          decimal(19,5)         
  DtStc                                    smalldatetime         
  QuantF                                   smallint(5,0)         
  QuantV                                   smallint(5,0)         
  chComp                                   bigint(19,0)          
  Comp                                     smallint(5,0)         
  Lote                                     bigint(19,0)          
  chPai2                                   bigint(19,0)          
  OrcIndex                                 smallint(5,0)         
  PrazoEnt                                 smalldatetime         
  ChLinPlan                                bigint(19,0)          
  Reembolso                                bigint(19,0)          
  ModoEntrega                              bigint(19,0)          
  Referencia                               bigint(19,0)          
  ValorOferta                              decimal(19,5)         
  Pontos                                   smallint(5,0)         
  QTC                                      decimal(19,3)         
  DescEX                                   decimal(19,5)         
  QTC2                                     decimal(19,3)         
  Prioridade                               tinyint(3,0)          
  Calibre                                  tinyint(3,0)          
  Posto                                    varchar(3)            
  Estado                                   tinyint(3,0)          
  PVMedio                                  decimal(19,5)         
  PVComissao                               decimal(19,5)         
  PVProvisorio                             decimal(19,5)         
  CHQData                                  smalldatetime         
  CHQNumero                                varchar(20)           
  CHQBanco                                 bigint(19,0)          
  Indice                                   smallint(5,0)         
  IOStatus                                 smallint(5,0)         
  VendedorInt                              bigint(19,0)          
  VendedorExt                              bigint(19,0)          
  TpIva                                    tinyint(3,0)          
```

**Key columns:**
- `Chave` — surrogate PK
- `Documento` → Doc001.Chave — parent document
- `ChaveProd` → Artigos.Chave — article/product
- `Descricao` — line description (may differ from article name)
- `Quantidade` — quantity
- `Punit` — unit price
- `Valor` — line total (Quantidade × Punit × discount)
- `Desconto` — discount string (e.g. '10+5')
- `Iva` — VAT rate
- `PCusto` — cost price
- `PVenda` — sale price
- `TpLinha` — line type (0=article, 1=text, 2=subtotal, ...)
- `Armazem` → Armazens
- `Obras` → project/work order reference

**Sales by article query:**
```sql
SELECT l.ChaveProd, l.Descricao, SUM(l.Quantidade) AS Qtd, SUM(l.Valor) AS Total
FROM Doc001 d JOIN LinDoc001 l ON d.Chave = l.Documento
WHERE d.TipoDoc = 1 AND d.Data >= '2026-01-01' AND d.Data < '2027-01-01'
GROUP BY l.ChaveProd, l.Descricao ORDER BY Total DESC
```

### Artigos — Products / Articles
rows=2720
```
  Chave                                    bigint(19,0)           PK
  DC                                       smalldatetime         
  OC                                       bigint(19,0)          
  DUA                                      smalldatetime         
  OUA                                      bigint(19,0)          
  Codigo                                   varchar(10)           
  Nome                                     varchar(120)          
  Abreviatura                              varchar(50)           
  CodBarras                                varchar(20)           
  CodBarras2                               varchar(20)           
  Ref                                      varchar(15)           
  Tipo                                     tinyint(3,0)          
  Tipo2                                    tinyint(3,0)          
  Hist                                     tinyint(3,0)          
  Listar                                   tinyint(3,0)          
  Predefinido                              tinyint(3,0)          
  chPai                                    bigint(19,0)          
  Pvenda                                   decimal(19,5)         
  PVenda2                                  decimal(19,5)         
  PrecoOferta                              decimal(19,5)         
  DAP                                      smalldatetime         
  OAP                                      bigint(19,0)          
  Obs                                      varchar(400)          
  Iva                                      bigint(19,0)          
  IvaValor                                 decimal(19,5)         
  Desc1                                    decimal(9,3)          
  Desc2                                    decimal(9,3)          
  Desc3                                    decimal(9,3)          
  DescMax                                  decimal(9,3)          
  DescQuant                                decimal(9,3)          
  Desconto                                 decimal(9,3)          
  UnPc                                     bigint(19,0)          
  UnStc                                    bigint(19,0)          
  UnCusto                                  bigint(19,0)          
  UnVenda                                  bigint(19,0)          
  UnAlternativa                            bigint(19,0)          
  UnCons                                   bigint(19,0)          
  UnTipo                                   bigint(19,0)          
  UnCalc                                   bigint(19,0)          
  UnAprov                                  bigint(19,0)          
  UnEmb                                    bigint(19,0)          
  FactorConv                               decimal(19,5)         
  SoEmb                                    tinyint(3,0)          
  QtEmb                                    decimal(19,3)         
  TipoEmbalagem                            bigint(19,0)          
  QuantMinEnc                              decimal(19,3)         
  QuantMultiplaEnc                         decimal(19,3)         
  StcReal                                  decimal(19,3)         
  StcRes                                   decimal(19,3)         
  StcPed                                   decimal(19,3)         
  StcDisp                                  decimal(19,3)         
  StcMin                                   decimal(19,3)         
  StcMax                                   decimal(19,3)         
  StcSeg                                   decimal(19,3)         
  StcCat                                   decimal(19,3)         
  StcEnc                                   decimal(19,3)         
  StcFirme                                 decimal(19,3)         
  StcCli                                   decimal(19,3)         
  StcFor                                   decimal(19,3)         
  SemStc                                   tinyint(3,0)          
  Localizacao                              varchar(20)           
  DUE                                      smalldatetime         
  DUS                                      smalldatetime         
  PCUltimo                                 decimal(19,5)         
  PCMedio                                  decimal(19,5)         
  PUE                                      decimal(19,5)         
  PcExtra                                  decimal(19,5)         
  TotCompras                               decimal(19,3)         
  TotValor                                 decimal(19,5)         
  Encargos                                 decimal(19,5)         
  FornPref                                 bigint(19,0)          
  QUE                                      decimal(19,3)         
  QUS                                      decimal(19,3)         
  PUS                                      decimal(19,5)         
  FUE                                      bigint(19,0)          
  MTol                                     decimal(9,3)          
  MMin                                     decimal(9,3)          
  MMarc                                    decimal(9,3)          
  Ctb                                      varchar(10)           
  CtbC                                     varchar(10)           
  CtbI                                     varchar(10)           
  CtbD                                     varchar(10)           
  CtbA                                     varchar(10)           
  Tara                                     bigint(19,0)          
  Seccao                                   bigint(19,0)          
  ComVend                                  decimal(19,5)         
  Anexos                                   smallint(5,0)         
  Etiquetas                                tinyint(3,0)          
  Art                                      bigint(19,0)          
  NumSerie                                 tinyint(3,0)          
  Promocao                                 tinyint(3,0)          
  Peso                                     decimal(19,3)         
  Enviado                                  tinyint(3,0)          
  EtiqEmb                                  tinyint(3,0)          
  TpComissao                               bigint(19,0)          
  Imp                                      tinyint(3,0)          
  Estado                                   smallint(5,0)         
  Lote                                     tinyint(3,0)          
  Tamanho                                  bigint(19,0)          
  Modelo                                   bigint(19,0)          
  Referencia                               bigint(19,0)          
  GSTC                                     tinyint(3,0)          
  SoEncomenda                              tinyint(3,0)          
  IntervaloEnc                             smallint(5,0)         
  CoeficienteSeg                           smallint(5,0)         
  Bloqueado                                tinyint(3,0)          
  LeadTime                                 smallint(5,0)         
  Composicao                               varchar(30)           
  Dono                                     bigint(19,0)          
  Tecla                                    varchar(50)           
  Pontos                                   tinyint(3,0)          
  PontosTroca                              tinyint(3,0)          
  Extra                                    tinyint(3,0)          
  POS                                      tinyint(3,0)          
  Classificacao                            bigint(19,0)          
  IOStatus                                 smallint(5,0)         
  Rotacao                                  decimal(19,3)         
  RotacaoExist                             decimal(19,3)         
  RotacaoVend                              decimal(19,3)         
  StcMedio                                 decimal(19,3)         
  Revisto                                  tinyint(3,0)          
  Web                                      smallint(5,0)         
  DetalheWeb                               varchar(200)          
  DetalheWeb2                              varchar(200)          
  CatalogoPDF                              image(2147483647)      NULL
  TipoSAFT                                 varchar(50)           
```

**Key columns:**
- `Chave` — surrogate PK, referenced by LinDoc001.ChaveProd
- `Nome` — article description/name
- `ChPai` → Artigos.Chave — **family/parent article** (self-referential hierarchy)
  - Root articles (ChPai=0 or ChPai=Chave) are **families**
  - Child articles belong to that family
- `Codigo` — article code
- `PVenda1`..`PVenda5` — price tiers
- `PCusto` — cost price
- `IVA` → IVA table
- `Activo` / `Inactivo` — active flag
- `Stock` — manages stock

**Sales by family query:**
```sql
SELECT f.Chave, f.Nome AS Familia, SUM(l.Valor) AS Total
FROM Doc001 d
JOIN LinDoc001 l ON d.Chave = l.Documento
JOIN Artigos a ON a.Chave = l.ChaveProd
JOIN Artigos f ON f.Chave = a.ChPai   -- family = parent article
WHERE d.TipoDoc = 1 AND d.Data >= '2026-01-01' AND d.Data < '2027-01-01'
GROUP BY f.Chave, f.Nome ORDER BY Total DESC
```

### Entidades — Customers / Suppliers / Contacts
rows=1955
```
  Chave                                    bigint(19,0)           PK
  Tipo                                     tinyint(3,0)          
  Codigo                                   varchar(10)           
  Nome                                     varchar(100)          
  Morada                                   varchar(75)           
  Localidade                               varchar(75)           
  CPostal                                  varchar(75)           
  Telefone1                                varchar(20)           
  Telefone2                                varchar(20)           
  Telefone3                                varchar(20)           
  Email                                    varchar(50)           
  Hist                                     tinyint(3,0)          
  Listar                                   tinyint(3,0)          
  Abrev                                    varchar(50)           
  DC                                       smalldatetime         
  OC                                       bigint(19,0)          
  DUA                                      smalldatetime         
  DUT                                      smalldatetime         
  OUA                                      bigint(19,0)          
  Fax                                      varchar(20)           
  NCont                                    varchar(20)           
  Obs                                      varchar(400)          
  Expedicao                                bigint(19,0)          
  CondPag                                  bigint(19,0)          
  ModoPag                                  bigint(19,0)          
  Zona                                     bigint(19,0)          
  Vendedor                                 bigint(19,0)          
  Lingua                                   bigint(19,0)          
  Moeda                                    bigint(19,0)          
  Desconto                                 decimal(19,5)         
  ... (+89 more columns)
```
**Key columns:**
- `Chave` — PK, referenced by Doc001.Entidade
- `Nome` — entity name
- `NIF` / `NIFPais` — tax ID
- `Tipo` — entity type (C=customer, F=supplier, O=other)

### TiposDoc — Document Types
Lookup of document types (invoice, quote, order, credit note, ...). Referenced by `Doc001.TipoDoc`.
rows=35
```
  Chave                                    bigint(19,0)          PK
  DC                                       smalldatetime
  OC                                       bigint(19,0)
  DUA                                      smalldatetime
  OUA                                      bigint(19,0)
  Nome                                     varchar(30)
  Codigo                                   varchar(3)
  Abreviatura                              varchar(10)
  Hist                                     tinyint(3,0)
  Numerador                                bigint(19,0)
  Listar                                   tinyint(3,0)
  Predefinido                              tinyint(3,0)
  Status                                   tinyint(3,0)
  Obs                                      varchar(500)
  Op                                       tinyint(3,0)
  TipoTab                                  tinyint(3,0)
  Data                                     tinyint(3,0)
  Dt                                       smalldatetime
  AnulApg                                  tinyint(3,0)
  TpDesc                                   tinyint(3,0)
  TpCCO                                    bigint(19,0)
  Entidade                                 tinyint(3,0)
  Mensagem                                 varchar(500)
  Credito                                  tinyint(3,0)
  Anexos                                   smallint(5,0)
  Armazem                                  tinyint(3,0)
  vRef                                     tinyint(3,0)
  Sinal                                    smallint(5,0)
  Classif                                  tinyint(3,0)
  doc_auto                                 bigint(19,0)
  TpCredito                                tinyint(3,0)
  CredForn                                 tinyint(3,0)
  TipoCTb                                  bigint(19,0)
  Serie                                    tinyint(3,0)
  ControloDesc                             tinyint(3,0)
  Margem                                   tinyint(3,0)
  TpLinhaPsion                             bigint(19,0)
  TotalNulo                                tinyint(3,0)
  Etiqueta                                 tinyint(3,0)
  chPai                                    bigint(19,0)
  DocAuto                                  bigint(19,0)
  TpchPai                                  tinyint(3,0)
  Pontos                                   tinyint(3,0)
  Doc_AutoPos                              tinyint(3,0)
  Cartao                                   tinyint(3,0)
  Reembolso                                tinyint(3,0)
  Mercado                                  bigint(19,0)
  DUT                                      tinyint(3,0)
  DataAlt                                  tinyint(3,0)
  Liquidacao                               tinyint(3,0)
  RecAdiantamento                          bigint(19,0)
  OrdPagamento                             bigint(19,0)
  TpIntAn                                  bigint(19,0)
  EmailSMTP                                varchar(200)          NULL
  EmailBody                                text(2147483647)
  EmailSubject                             varchar(200)
  SaveTo                                   varchar(200)
  certificacao                             tinyint(3,0)
  SGQ1                                     varchar(50)
  SGQ2                                     varchar(50)
  SAFT                                     varchar(50)
  IOLinha1                                 bigint(19,0)          NULL
  IOLinha2                                 bigint(19,0)          NULL
  TipoDocAT                                bigint(19,0)          NULL
```

**Key columns:**
- `Chave` — surrogate PK, referenced by `Doc001.TipoDoc`
- `Codigo` — short type code (varchar(3), e.g. FA, OR, NC)
- `Nome` — document type name (e.g. Fatura, Orçamento)
- `Abreviatura` — abbreviation used on printed documents
- `Numerador` → Numeradores.Chave — numbering sequence
- `Sinal` — sign of the document's effect (+/-) on stock / account
- `TpCCO` → TiposDocCCO — current-account document type
- `TipoCTb` → TiposDocCtb — accounting document type
- `TipoDocAT` → TiposDocAT.Chave / `SAFT` — Portuguese fiscal (AT/SAF-T) document type mapping
- `certificacao` — whether documents of this type are fiscally certified
- `Predefinido` / `Listar` / `Status` / `Hist` — default, visibility, status, and history flags

## DevDB — Full Table Inventory

Total: **228 tables**, 12 views

### Group: SYS (33 tables)

| Table | Rows | Cols |
|---|---|---|
| SYS00 | 90 | 11 |
| SYS01 | 196 | 12 |
| SYS01_Catalogo | 18 | 12 |
| SYS02 | 1409 | 24 |
| SYS03 | 8 | 36 |
| SYS07 | 734 | 36 |
| SYS08 | 138 | 3 |
| SYS10 | 5 | 8 |
| SYS11 | 14 | 11 |
| SYS12 | 5 | 7 |
| SYS13 | 15 | 6 |
| SYS14 | 1 | 7 |
| SYS23 | 1 | 7 |
| SYS60 | 5 | 24 |
| SYS61 | 24 | 8 |
| SYS63 | 13 | 6 |
| SYS64 | 3 | 3 |
| SYS98 | 211 | 5 |
| SYS99 | 1510 | 58 |

### Group: CRM (19 tables)

| Table | Rows | Cols |
|---|---|---|
| CRM_99 | 43 | 17 |
| CRM_Anexos | 2277 | 12 |
| CRM_Atividades | 160 | 26 |
| CRM_AtividadesEstados | 321 | 7 |
| CRM_Comunicacoes | 18 | 11 |
| CRM_Emails | 3438 | 16 |
| CRM_Enderecos | 3536 | 10 |
| CRM_Estados | 16 | 10 |
| CRM_GruposProcessos | 3 | 8 |
| CRM_Inbox | 7 | 23 |
| CRM_ProcessosAtividades | 70 | 4 |
| CRM_TipoAtividadesProcessos | 36 | 19 |
| CRM_Transicoes | 90 | 3 |
| CRM_Utilizadores | 7 | 13 |
| CRM_UtilizadoresInbox | 13 | 7 |

### Group: IO (7 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ATR (5 tables)

| Table | Rows | Cols |
|---|---|---|
| ATR_Atributos | 795 | 12 |
| ATR_ContextosTiposAtributos | 30 | 11 |
| ATR_Listas | 4 | 6 |
| ATR_RelContextosAtributos | 40 | 11 |
| ATR_TiposDados | 16 | 12 |

### Group: Pos (4 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Doc (3 tables)

| Table | Rows | Cols |
|---|---|---|
| Doc001 | 21286 | 80 |
| Doc001_Delete | 603 | 80 |
| Doc005 | 3 | 3 |

### Group: LinDoc (3 tables)

| Table | Rows | Cols |
|---|---|---|
| LinDoc001 | 63769 | 84 |

### Group: LinPlan (2 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Lindoc (2 tables)

| Table | Rows | Cols |
|---|---|---|
| Lindoc001_Delete | 1939 | 84 |
| Lindoc005 | 16 | 4 |

### Group: Plan (2 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: AVencimento (1 tables)

| Table | Rows | Cols |
|---|---|---|
| AVencimento | 3 | 17 |

### Group: Acessos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Acessos | 3 | 9 |

### Group: Anexos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Anexos | 12 | 20 |

### Group: AnexosCat (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: AnexosGrpDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| AnexosGrpDoc | 5 | 9 |

### Group: AnexosGrpDocTp (1 tables)

| Table | Rows | Cols |
|---|---|---|
| AnexosGrpDocTp | 15 | 4 |

### Group: AnexosIndexantes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: AnexosPalavrasChave (1 tables)

| Table | Rows | Cols |
|---|---|---|
| AnexosPalavrasChave | 11 | 4 |

### Group: AnexosTiposDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| AnexosTiposDoc | 57 | 10 |

### Group: AnexosTiposDocIndexantes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtArm (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtArm | 3026 | 29 |

### Group: ArtComp (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtDim (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtEmp (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtEmp | 1958 | 51 |

### Group: ArtEnt (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtLng (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtMerc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtMerc | 6 | 25 |

### Group: ArtProp (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtPsion (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtRef (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtSubst (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtUnid (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtUnidWeb (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Artigos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Artigos | 2720 | 126 |

### Group: Avaliacoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Avaliacoes | 39 | 16 |

### Group: Bancos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Bancos | 25 | 15 |

### Group: CCO (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CCO | 34906 | 38 |

### Group: CCOLIQ (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CCOLIQ | 56566 | 9 |

### Group: CTB (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CTB | 23765 | 14 |

### Group: Carteiras (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Carteiras | 10 | 13 |

### Group: Cartoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Chats (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Chats | 37 | 14 |

### Group: Classificacoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Classificadores (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Comissoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ComissoesPeriodos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: CondPag (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CondPag | 15 | 16 |

### Group: Consumos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ContCred (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ContCred | 4 | 15 |

### Group: Contactos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Contactos | 30 | 9 |

### Group: DocCart (1 tables)

| Table | Rows | Cols |
|---|---|---|
| DocCart | 25 | 4 |

### Group: Entidades (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Entidades | 1955 | 119 |

### Group: EntidadesRelacoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| EntidadesRelacoes | 1898 | 8 |

### Group: Eventos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Expedicoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Expedicoes | 21 | 11 |

### Group: FO (1 tables)

| Table | Rows | Cols |
|---|---|---|
| FO | 9630 | 69 |

### Group: Fields (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Fields | 370 | 11 |

### Group: GrTam (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: GrpDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| GrpDoc | 21 | 12 |

### Group: GrpDocTp (1 tables)

| Table | Rows | Cols |
|---|---|---|
| GrpDocTp | 67 | 4 |

### Group: Hardware (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Hardware | 2 | 8 |

### Group: Horarios (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ImageRead (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ImageRead | 6 | 4 |

### Group: Impressoras (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Impressoras | 5 | 12 |

### Group: LangFields (1 tables)

| Table | Rows | Cols |
|---|---|---|
| LangFields | 597 | 11 |

### Group: Language (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Language | 2 | 8 |

### Group: Licencas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Licencas | 32 | 18 |

### Group: LinDOc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| LinDOc001_GrFamilia | 57820 | 2 |

### Group: Linguas (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Lotes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Lotes | 1 | 15 |

### Group: ModoPag (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ModoPag | 1 | 13 |

### Group: ModosEntrega (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Moeda (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Moeda | 3 | 18 |

### Group: MultiDim (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Numeradores (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Numeradores | 47 | 12 |

### Group: Operacoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: PckTransactions (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Pessoal (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Planos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: PortalBanners (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalBanners | 136 | 10 |

### Group: PortalContacts (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalContacts | 2 | 22 |

### Group: PortalDestak (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: PortalDetails (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalDetails | 74 | 14 |

### Group: PortalDetailsGeral (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalDetailsGeral | 8 | 13 |

### Group: PortalFields (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalFields | 8 | 11 |

### Group: PortalLangFields (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalLangFields | 24 | 11 |

### Group: PortalLanguage (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalLanguage | 2 | 8 |

### Group: PortalMenu (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalMenu | 6 | 10 |

### Group: PortalMenuEng (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalMenuEng | 5 | 10 |

### Group: PortalNews (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalNews | 19 | 11 |

### Group: PortalPartners (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalPartners | 4 | 11 |

### Group: PortalProdDetails (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalProdDetails | 32 | 19 |

### Group: PortalProdFields (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalProdFields | 32 | 12 |

### Group: PortalSubMenu (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalSubMenu | 11 | 10 |

### Group: PortalSubMenuEng (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalSubMenuEng | 11 | 11 |

### Group: PortalSubSubjects (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalSubSubjects | 3 | 11 |

### Group: PortalTestimony (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: PosOperacoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Postos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Postos | 13 | 47 |

### Group: Priority (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Priority | 3 | 10 |

### Group: PsionCab (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: PsionLin (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: RegTpIVA (1 tables)

| Table | Rows | Cols |
|---|---|---|
| RegTpIVA | 19 | 6 |

### Group: RegimesIVA (1 tables)

| Table | Rows | Cols |
|---|---|---|
| RegimesIVA | 13 | 17 |

### Group: RequestTypes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| RequestTypes | 5 | 9 |

### Group: Requests (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Requests | 22 | 25 |

### Group: Rotas (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: SNCFiles (1 tables)

| Table | Rows | Cols |
|---|---|---|
| SNCFiles | 12 | 5 |

### Group: SYSLOCK (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: SYSLOG (1 tables)

| Table | Rows | Cols |
|---|---|---|
| SYSLOG | 6260 | 10 |

### Group: SYSProfiles (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: SYSProfilesPerm (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Seccoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Sessoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Severity (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Severity | 3 | 10 |

### Group: Software (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Software | 16 | 8 |

### Group: Status (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Status | 6 | 8 |

### Group: TabClassif (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Taras (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Tasks (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Tasks | 13 | 20 |

### Group: Telefone (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Telefone | 105 | 5 |

### Group: Tempos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TiposComissao (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TiposContas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposContas | 6 | 13 |

### Group: TiposDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDoc | 35 | 64 |

### Group: TiposDocAT (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocAT | 24 | 9 |

### Group: TiposDocCCO (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocCCO | 37 | 45 |

### Group: TiposDocCtb (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocCtb | 9 | 22 |

### Group: TiposDocLin (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocLin | 110 | 4 |

### Group: TiposDocLinCtb (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocLinCtb | 10 | 16 |

### Group: TiposDocPst (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocPst | 214 | 11 |

### Group: TiposEmbalagem (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TiposInt (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposInt | 16 | 28 |

### Group: TiposIntL (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposIntL | 24 | 13 |

### Group: TiposIva (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposIva | 4 | 14 |

### Group: TiposLin (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposLin | 46 | 64 |

### Group: TiposLinSTC (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposLinSTC | 43 | 34 |

### Group: TiposSerieNum (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposSerieNum | 124 | 7 |

### Group: TiposSerieTpDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpCCO (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpConf (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpEtiq (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TmpEtiq | 2504 | 9 |

### Group: TmpInt (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TmpInt | 8 | 77 |

### Group: TmpIntAn (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpMultiDim (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpObras (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TpContactos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpContactos | 1 | 13 |

### Group: TpContas (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TpDocATSerie (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpDocATSerie | 8 | 4 |

### Group: TpDocML (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TpEnt (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Unidades (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Unidades | 2 | 17 |

### Group: Vendedores (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Vendedores | 11 | 24 |

### Group: Zonas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Zonas | 1 | 13 |

### Group: image (1 tables)

| Table | Rows | Cols |
|---|---|---|
| image | 13 | 4 |

### Group: sys (1 tables)

| Table | Rows | Cols |
|---|---|---|
| sys99n | 8 | 58 |

### Group: tmporder (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: tmpsession (1 tables)

| Table | Rows | Cols |
|---|---|---|
| tmpsession | 11 | 8 |

## DOClinic — Full Table Inventory

Total: **190 tables**, 49 views

### Group: SYS (25 tables)

| Table | Rows | Cols |
|---|---|---|
| SYS00 | 159 | 11 |
| SYS01 | 403 | 10 |
| SYS02 | 3416 | 25 |
| SYS03 | 15 | 25 |
| SYS05 | 2 | 4 |
| SYS07 | 1565 | 38 |
| SYS08 | 210 | 3 |
| SYS60 | 11 | 22 |
| SYS61 | 1 | 9 |
| SYS62 | 1 | 4 |
| SYS63 | 4 | 6 |
| SYS70 | 2 | 21 |
| SYS81 | 2 | 4 |
| SYS98 | 475 | 16 |
| SYS99 | 3891 | 60 |

### Group: CRM (5 tables)

| Table | Rows | Cols |
|---|---|---|
| CRM11 | 4 | 9 |
| CRM12 | 12 | 9 |
| CRM13 | 24 | 4 |
| CRM14 | 10 | 4 |
| CRM_Inbox | 1 | 20 |

### Group: LinDoc (4 tables)

| Table | Rows | Cols |
|---|---|---|
| LinDoc001 | 7937 | 67 |

### Group: A (3 tables)

| Table | Rows | Cols |
|---|---|---|
| A | 101 | 38 |

### Group: ESP (3 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: SNS (3 tables)

| Table | Rows | Cols |
|---|---|---|
| SNS_LP | 6892 | 4 |
| SNS_ListaErros | 23 | 5 |

### Group: SYSER (3 tables)

| Table | Rows | Cols |
|---|---|---|
| SYSER01 | 25 | 19 |
| SYSER02 | 56 | 6 |
| SYSER03 | 6 | 3 |

### Group: Doc (2 tables)

| Table | Rows | Cols |
|---|---|---|
| Doc001 | 6389 | 88 |

### Group: Reservas (2 tables)

| Table | Rows | Cols |
|---|---|---|
| Reservas | 11306 | 167 |

### Group: WebLoginEntidades (2 tables)

| Table | Rows | Cols |
|---|---|---|
| WebLoginEntidades | 28 | 16 |
| WebLoginEntidades_TMP | 35 | 3 |

### Group: Anexos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtArm (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtArm | 6 | 25 |

### Group: ArtComp (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtComp | 1 | 6 |

### Group: ArtDim (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtLng (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtMedico (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtMedico | 44 | 7 |

### Group: ArtMerc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtMerc | 343 | 19 |

### Group: ArtMercHon (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtMercHon | 258 | 19 |

### Group: Artigos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Artigos | 196 | 101 |

### Group: Bancos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Bancos | 12 | 15 |

### Group: CCO (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CCO | 6026 | 41 |

### Group: CCOLIQ (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CCOLIQ | 6025 | 9 |

### Group: CTB (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Carimbos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Carimbos | 17 | 9 |

### Group: CartEnt (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Carteiras (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Carteiras | 10 | 13 |

### Group: Comissoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ComissoesTpEnt (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: CondPag (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CondPag | 6 | 16 |

### Group: ConfigResults (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ConfigResults | 5 | 31 |

### Group: Consumos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ContCred (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Contactos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Contactos | 542 | 8 |

### Group: Cred (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Cred | 6584 | 2 |

### Group: CredenciaisSNS (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CredenciaisSNS | 113560 | 12 |

### Group: Declaracoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Declaracoes | 9194 | 5 |

### Group: Devolucoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Diagnosticos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Diagnosticos | 1200 | 14 |

### Group: DiagnosticosSnomed (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Dias (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Dias | 800 | 7 |

### Group: DocCPart (1 tables)

| Table | Rows | Cols |
|---|---|---|
| DocCPart | 5 | 4 |

### Group: DocCart (1 tables)

| Table | Rows | Cols |
|---|---|---|
| DocCart | 34 | 4 |

### Group: ERPalavrasVox (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ERPalavrasVox | 2 | 8 |

### Group: EmpresaConvencoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| EmpresaConvencoes | 59 | 7 |

### Group: EmpresaSeries (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: EmpresasMeiosLiquidacao (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Entidades (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Entidades | 28772 | 149 |

### Group: EntidadesLP (1 tables)

| Table | Rows | Cols |
|---|---|---|
| EntidadesLP | 11800 | 142 |

### Group: EntidadesSeries (1 tables)

| Table | Rows | Cols |
|---|---|---|
| EntidadesSeries | 23 | 4 |

### Group: EntidadesTPA (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Especialidades (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Especialidades | 31 | 12 |

### Group: Estados (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Estados | 103 | 23 |

### Group: Expedicoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Expedicoes | 2 | 11 |

### Group: FO (1 tables)

| Table | Rows | Cols |
|---|---|---|
| FO | 1 | 118 |

### Group: Familias (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: GrTam (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: GrpArtigos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| GrpArtigos | 50 | 25 |

### Group: GrpDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| GrpDoc | 13 | 11 |

### Group: GrpDocTp (1 tables)

| Table | Rows | Cols |
|---|---|---|
| GrpDocTp | 48 | 3 |

### Group: GrpRec (1 tables)

| Table | Rows | Cols |
|---|---|---|
| GrpRec | 128 | 4 |

### Group: ImpressoesEnvios (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Impressoras (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Impressoras | 14 | 12 |

### Group: Linguas (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ListaLP (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ListaLP_SNS | 6916 | 3 |

### Group: Locais (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Locais | 3 | 12 |

### Group: LocaisPrescricaoComissoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Lotes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Lotes | 1 | 13 |

### Group: ModoPag (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ModoPag | 2 | 13 |

### Group: Moeda (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Moeda | 2 | 18 |

### Group: MovCCOCart (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: MultiDim (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: NHParticulares (1 tables)

| Table | Rows | Cols |
|---|---|---|
| NHParticulares | 525 | 1 |

### Group: Numeradores (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Numeradores | 53 | 12 |

### Group: Operacoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Operacoes | 33 | 15 |

### Group: OrigensEntidades (1 tables)

| Table | Rows | Cols |
|---|---|---|
| OrigensEntidades | 8 | 4 |

### Group: PagamentosTPA (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PagamentosTPA | 1 | 12 |

### Group: Paineis (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Paineis | 25 | 8 |

### Group: PaineisTpPedidosExtras (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PaineisTpPedidosExtras | 141 | 3 |

### Group: PedidosRecolha (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Pessoal (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Pessoal | 1 | 21 |

### Group: Pos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Postos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Postos | 48 | 50 |

### Group: Prescritores (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Prescritores | 8937 | 27 |

### Group: PrescritoresLocais (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PrescritoresLocais | 19391 | 5 |

### Group: RefSIBSHist (1 tables)

| Table | Rows | Cols |
|---|---|---|
| RefSIBSHist | 44 | 2 |

### Group: RegTpIVA (1 tables)

| Table | Rows | Cols |
|---|---|---|
| RegTpIVA | 16 | 5 |

### Group: RegimesIVA (1 tables)

| Table | Rows | Cols |
|---|---|---|
| RegimesIVA | 4 | 16 |

### Group: Regras (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Regras | 774 | 25 |

### Group: ReservasCredenciais (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ReservasEnvios (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ReservasEnvios | 10680 | 16 |

### Group: ReservasEstados (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ReservasEstados | 83780 | 8 |

### Group: ReservasHist (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ReservasPedidos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ReservasServicos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ReservasServicos | 11336 | 13 |

### Group: Rotas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Rotas | 1 | 17 |

### Group: SYSDefaults (1 tables)

| Table | Rows | Cols |
|---|---|---|
| SYSDefaults | 9 | 11 |

### Group: SYSLOCK (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: SYSLOG (1 tables)

| Table | Rows | Cols |
|---|---|---|
| SYSLOG | 38507 | 10 |

### Group: Seccoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Seccoes | 15 | 12 |

### Group: Sessoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: SmsQueue (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TMP (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TextoModificador (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TextoModificador | 63 | 8 |

### Group: TimeService (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TiposContas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposContas | 4 | 13 |

### Group: TiposDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDoc | 28 | 57 |

### Group: TiposDocAT (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocAT | 21 | 9 |

### Group: TiposDocCCO (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocCCO | 42 | 44 |

### Group: TiposDocCtb (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocCtb | 18 | 23 |

### Group: TiposDocLin (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocLin | 64 | 4 |

### Group: TiposDocLinCtb (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocLinCtb | 14 | 16 |

### Group: TiposDocPst (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocPst | 240 | 11 |

### Group: TiposInt (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposInt | 12 | 27 |

### Group: TiposIntL (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposIntL | 78 | 13 |

### Group: TiposIva (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposIva | 5 | 14 |

### Group: TiposLin (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposLin | 36 | 60 |

### Group: TiposLinSTC (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposLinSTC | 11 | 34 |

### Group: TiposSerieNum (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposSerieNum | 126 | 5 |

### Group: TiposSerieTpDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposSerieTpDoc | 3 | 4 |

### Group: Titulos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Titulos | 21 | 15 |

### Group: Tmp (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Tmp | 12 | 25 |

### Group: TmpAgenda (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpCCO (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpCTB (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpConf (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpEncFact (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpEtiq (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpInt (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpIntAn (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpMultiDim (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpReservas (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TpArtigos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpArtigos | 4 | 15 |

### Group: TpContactos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpContactos | 6 | 13 |

### Group: TpContas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpContas | 5 | 6 |

### Group: TpDocATSerie (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpDocATSerie | 14 | 4 |

### Group: TpDocML (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TpEnt (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpEnt | 3 | 13 |

### Group: Unidades (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Unidades | 5 | 17 |

### Group: Vendedores (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Vendedores | 1 | 23 |

### Group: WebLidos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| WebLidos | 69779 | 8 |

### Group: WebLogin (1 tables)

| Table | Rows | Cols |
|---|---|---|
| WebLogin | 14 | 18 |

### Group: WebMensagens (1 tables)

| Table | Rows | Cols |
|---|---|---|
| WebMensagens | 12 | 23 |

### Group: WebTipoMensagens (1 tables)

| Table | Rows | Cols |
|---|---|---|
| WebTipoMensagens | 3 | 4 |

### Group: WorkMail (1 tables)

| Table | Rows | Cols |
|---|---|---|
| WorkMail | 17 | 15 |

### Group: WorkMailAnexos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| WorkMailAnexos | 18 | 6 |

### Group: Zonas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Zonas | 27 | 15 |

### Group: _A_ESP_ResultadoEnvioSync (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: sysdiagrams (1 tables)

| Table | Rows | Cols |
|---|---|---|

## DevCare — Full Table Inventory

Total: **190 tables**, 49 views

### Group: SYS (25 tables)

| Table | Rows | Cols |
|---|---|---|
| SYS00 | 159 | 11 |
| SYS01 | 403 | 10 |
| SYS02 | 3416 | 25 |
| SYS03 | 15 | 25 |
| SYS05 | 2 | 4 |
| SYS07 | 1565 | 38 |
| SYS08 | 210 | 3 |
| SYS60 | 11 | 22 |
| SYS61 | 1 | 9 |
| SYS62 | 1 | 4 |
| SYS63 | 4 | 6 |
| SYS70 | 2 | 21 |
| SYS81 | 2 | 4 |
| SYS98 | 475 | 16 |
| SYS99 | 3891 | 60 |

### Group: CRM (5 tables)

| Table | Rows | Cols |
|---|---|---|
| CRM11 | 4 | 9 |
| CRM12 | 12 | 9 |
| CRM13 | 24 | 4 |
| CRM14 | 10 | 4 |
| CRM_Inbox | 1 | 20 |

### Group: LinDoc (4 tables)

| Table | Rows | Cols |
|---|---|---|
| LinDoc001 | 7937 | 67 |

### Group: A (3 tables)

| Table | Rows | Cols |
|---|---|---|
| A | 101 | 38 |

### Group: ESP (3 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: SNS (3 tables)

| Table | Rows | Cols |
|---|---|---|
| SNS_LP | 6892 | 4 |
| SNS_ListaErros | 23 | 5 |

### Group: SYSER (3 tables)

| Table | Rows | Cols |
|---|---|---|
| SYSER01 | 25 | 19 |
| SYSER02 | 56 | 6 |
| SYSER03 | 6 | 3 |

### Group: Doc (2 tables)

| Table | Rows | Cols |
|---|---|---|
| Doc001 | 6389 | 88 |

### Group: Reservas (2 tables)

| Table | Rows | Cols |
|---|---|---|
| Reservas | 11306 | 167 |

### Group: WebLoginEntidades (2 tables)

| Table | Rows | Cols |
|---|---|---|
| WebLoginEntidades | 28 | 16 |
| WebLoginEntidades_TMP | 35 | 3 |

### Group: Anexos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtArm (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtArm | 6 | 25 |

### Group: ArtComp (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtComp | 1 | 6 |

### Group: ArtDim (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtLng (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtMedico (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtMedico | 44 | 7 |

### Group: ArtMerc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtMerc | 343 | 19 |

### Group: ArtMercHon (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtMercHon | 258 | 19 |

### Group: Artigos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Artigos | 196 | 101 |

### Group: Bancos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Bancos | 12 | 15 |

### Group: CCO (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CCO | 6026 | 41 |

### Group: CCOLIQ (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CCOLIQ | 6025 | 9 |

### Group: CTB (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Carimbos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Carimbos | 17 | 9 |

### Group: CartEnt (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Carteiras (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Carteiras | 10 | 13 |

### Group: Comissoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ComissoesTpEnt (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: CondPag (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CondPag | 6 | 16 |

### Group: ConfigResults (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ConfigResults | 5 | 31 |

### Group: Consumos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ContCred (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Contactos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Contactos | 542 | 8 |

### Group: Cred (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Cred | 6584 | 2 |

### Group: CredenciaisSNS (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CredenciaisSNS | 113560 | 12 |

### Group: Declaracoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Declaracoes | 9194 | 5 |

### Group: Devolucoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Diagnosticos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Diagnosticos | 1200 | 14 |

### Group: DiagnosticosSnomed (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Dias (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Dias | 800 | 7 |

### Group: DocCPart (1 tables)

| Table | Rows | Cols |
|---|---|---|
| DocCPart | 5 | 4 |

### Group: DocCart (1 tables)

| Table | Rows | Cols |
|---|---|---|
| DocCart | 34 | 4 |

### Group: ERPalavrasVox (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ERPalavrasVox | 2 | 8 |

### Group: EmpresaConvencoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| EmpresaConvencoes | 59 | 7 |

### Group: EmpresaSeries (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: EmpresasMeiosLiquidacao (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Entidades (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Entidades | 28772 | 149 |

### Group: EntidadesLP (1 tables)

| Table | Rows | Cols |
|---|---|---|
| EntidadesLP | 11800 | 142 |

### Group: EntidadesSeries (1 tables)

| Table | Rows | Cols |
|---|---|---|
| EntidadesSeries | 23 | 4 |

### Group: EntidadesTPA (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Especialidades (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Especialidades | 31 | 12 |

### Group: Estados (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Estados | 103 | 23 |

### Group: Expedicoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Expedicoes | 2 | 11 |

### Group: FO (1 tables)

| Table | Rows | Cols |
|---|---|---|
| FO | 1 | 118 |

### Group: Familias (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: GrTam (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: GrpArtigos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| GrpArtigos | 50 | 25 |

### Group: GrpDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| GrpDoc | 13 | 11 |

### Group: GrpDocTp (1 tables)

| Table | Rows | Cols |
|---|---|---|
| GrpDocTp | 48 | 3 |

### Group: GrpRec (1 tables)

| Table | Rows | Cols |
|---|---|---|
| GrpRec | 128 | 4 |

### Group: ImpressoesEnvios (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Impressoras (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Impressoras | 14 | 12 |

### Group: Linguas (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ListaLP (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ListaLP_SNS | 6916 | 3 |

### Group: Locais (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Locais | 3 | 12 |

### Group: LocaisPrescricaoComissoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Lotes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Lotes | 1 | 13 |

### Group: ModoPag (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ModoPag | 2 | 13 |

### Group: Moeda (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Moeda | 2 | 18 |

### Group: MovCCOCart (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: MultiDim (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: NHParticulares (1 tables)

| Table | Rows | Cols |
|---|---|---|
| NHParticulares | 525 | 1 |

### Group: Numeradores (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Numeradores | 53 | 12 |

### Group: Operacoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Operacoes | 33 | 15 |

### Group: OrigensEntidades (1 tables)

| Table | Rows | Cols |
|---|---|---|
| OrigensEntidades | 8 | 4 |

### Group: PagamentosTPA (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PagamentosTPA | 1 | 12 |

### Group: Paineis (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Paineis | 25 | 8 |

### Group: PaineisTpPedidosExtras (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PaineisTpPedidosExtras | 141 | 3 |

### Group: PedidosRecolha (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Pessoal (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Pessoal | 1 | 21 |

### Group: Pos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Postos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Postos | 48 | 50 |

### Group: Prescritores (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Prescritores | 8937 | 27 |

### Group: PrescritoresLocais (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PrescritoresLocais | 19391 | 5 |

### Group: RefSIBSHist (1 tables)

| Table | Rows | Cols |
|---|---|---|
| RefSIBSHist | 44 | 2 |

### Group: RegTpIVA (1 tables)

| Table | Rows | Cols |
|---|---|---|
| RegTpIVA | 16 | 5 |

### Group: RegimesIVA (1 tables)

| Table | Rows | Cols |
|---|---|---|
| RegimesIVA | 4 | 16 |

### Group: Regras (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Regras | 774 | 25 |

### Group: ReservasCredenciais (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ReservasEnvios (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ReservasEnvios | 10680 | 16 |

### Group: ReservasEstados (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ReservasEstados | 83780 | 8 |

### Group: ReservasHist (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ReservasPedidos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ReservasServicos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ReservasServicos | 11336 | 13 |

### Group: Rotas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Rotas | 1 | 17 |

### Group: SYSDefaults (1 tables)

| Table | Rows | Cols |
|---|---|---|
| SYSDefaults | 9 | 11 |

### Group: SYSLOCK (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: SYSLOG (1 tables)

| Table | Rows | Cols |
|---|---|---|
| SYSLOG | 38507 | 10 |

### Group: Seccoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Seccoes | 15 | 12 |

### Group: Sessoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: SmsQueue (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TMP (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TextoModificador (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TextoModificador | 63 | 8 |

### Group: TimeService (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TiposContas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposContas | 4 | 13 |

### Group: TiposDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDoc | 28 | 57 |

### Group: TiposDocAT (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocAT | 21 | 9 |

### Group: TiposDocCCO (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocCCO | 42 | 44 |

### Group: TiposDocCtb (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocCtb | 18 | 23 |

### Group: TiposDocLin (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocLin | 64 | 4 |

### Group: TiposDocLinCtb (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocLinCtb | 14 | 16 |

### Group: TiposDocPst (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocPst | 240 | 11 |

### Group: TiposInt (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposInt | 12 | 27 |

### Group: TiposIntL (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposIntL | 78 | 13 |

### Group: TiposIva (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposIva | 5 | 14 |

### Group: TiposLin (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposLin | 36 | 60 |

### Group: TiposLinSTC (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposLinSTC | 11 | 34 |

### Group: TiposSerieNum (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposSerieNum | 126 | 5 |

### Group: TiposSerieTpDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposSerieTpDoc | 3 | 4 |

### Group: Titulos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Titulos | 21 | 15 |

### Group: Tmp (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Tmp | 12 | 25 |

### Group: TmpAgenda (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpCCO (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpCTB (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpConf (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpEncFact (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpEtiq (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpInt (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpIntAn (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpMultiDim (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpReservas (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TpArtigos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpArtigos | 4 | 15 |

### Group: TpContactos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpContactos | 6 | 13 |

### Group: TpContas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpContas | 5 | 6 |

### Group: TpDocATSerie (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpDocATSerie | 14 | 4 |

### Group: TpDocML (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TpEnt (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpEnt | 3 | 13 |

### Group: Unidades (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Unidades | 5 | 17 |

### Group: Vendedores (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Vendedores | 1 | 23 |

### Group: WebLidos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| WebLidos | 69779 | 8 |

### Group: WebLogin (1 tables)

| Table | Rows | Cols |
|---|---|---|
| WebLogin | 14 | 18 |

### Group: WebMensagens (1 tables)

| Table | Rows | Cols |
|---|---|---|
| WebMensagens | 12 | 23 |

### Group: WebTipoMensagens (1 tables)

| Table | Rows | Cols |
|---|---|---|
| WebTipoMensagens | 3 | 4 |

### Group: WorkMail (1 tables)

| Table | Rows | Cols |
|---|---|---|
| WorkMail | 17 | 15 |

### Group: WorkMailAnexos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| WorkMailAnexos | 18 | 6 |

### Group: Zonas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Zonas | 27 | 15 |

### Group: _A_ESP_ResultadoEnvioSync (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: sysdiagrams (1 tables)

| Table | Rows | Cols |
|---|---|---|

## ForumSI — Full Table Inventory

Total: **241 tables**, 12 views

### Group: SYS (34 tables)

| Table | Rows | Cols |
|---|---|---|
| SYS00 | 90 | 11 |
| SYS00Nova | 73 | 11 |
| SYS01 | 196 | 12 |
| SYS01_Catalogo | 18 | 12 |
| SYS02 | 1409 | 24 |
| SYS03 | 8 | 36 |
| SYS07 | 734 | 36 |
| SYS08 | 138 | 3 |
| SYS10 | 5 | 8 |
| SYS11 | 14 | 11 |
| SYS12 | 5 | 7 |
| SYS13 | 15 | 6 |
| SYS14 | 1 | 7 |
| SYS23 | 1 | 7 |
| SYS60 | 5 | 24 |
| SYS61 | 24 | 8 |
| SYS63 | 13 | 6 |
| SYS64 | 3 | 3 |
| SYS98 | 211 | 5 |
| SYS99 | 1510 | 58 |

### Group: CRM (19 tables)

| Table | Rows | Cols |
|---|---|---|
| CRM_99 | 43 | 17 |
| CRM_Anexos | 2277 | 12 |
| CRM_Atividades | 160 | 26 |
| CRM_AtividadesEstados | 321 | 7 |
| CRM_Comunicacoes | 18 | 11 |
| CRM_Emails | 3438 | 16 |
| CRM_Enderecos | 3536 | 10 |
| CRM_Estados | 16 | 10 |
| CRM_GruposProcessos | 3 | 8 |
| CRM_Inbox | 7 | 23 |
| CRM_ProcessosAtividades | 70 | 4 |
| CRM_TipoAtividadesProcessos | 36 | 19 |
| CRM_Transicoes | 90 | 3 |
| CRM_Utilizadores | 7 | 13 |
| CRM_UtilizadoresInbox | 13 | 7 |

### Group: IO (7 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ATR (5 tables)

| Table | Rows | Cols |
|---|---|---|
| ATR_Atributos | 795 | 12 |
| ATR_ContextosTiposAtributos | 30 | 11 |
| ATR_Listas | 4 | 6 |
| ATR_RelContextosAtributos | 40 | 11 |
| ATR_TiposDados | 16 | 12 |

### Group: Clientes (4 tables)

| Table | Rows | Cols |
|---|---|---|
| Clientes2011 | 102 | 1 |
| Clientes2012 | 84 | 1 |
| Clientes2013 | 73 | 1 |
| Clientes2014 | 68 | 1 |

### Group: Pos (4 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Doc (3 tables)

| Table | Rows | Cols |
|---|---|---|
| Doc001 | 21294 | 80 |
| Doc001_Delete | 603 | 80 |
| Doc005 | 3 | 3 |

### Group: LinDoc (3 tables)

| Table | Rows | Cols |
|---|---|---|
| LinDoc001 | 63790 | 84 |

### Group: Chicken (2 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: LinPlan (2 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Lindoc (2 tables)

| Table | Rows | Cols |
|---|---|---|
| Lindoc001_Delete | 1939 | 84 |
| Lindoc005 | 16 | 4 |

### Group: Plan (2 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: AVencimento (1 tables)

| Table | Rows | Cols |
|---|---|---|
| AVencimento | 3 | 17 |

### Group: Acessos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Acessos | 3 | 9 |

### Group: Anexos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Anexos | 12 | 20 |

### Group: AnexosCat (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: AnexosGrpDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| AnexosGrpDoc | 5 | 9 |

### Group: AnexosGrpDocTp (1 tables)

| Table | Rows | Cols |
|---|---|---|
| AnexosGrpDocTp | 15 | 4 |

### Group: AnexosIndexantes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: AnexosPalavrasChave (1 tables)

| Table | Rows | Cols |
|---|---|---|
| AnexosPalavrasChave | 11 | 4 |

### Group: AnexosTiposDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| AnexosTiposDoc | 57 | 10 |

### Group: AnexosTiposDocIndexantes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtArm (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtArm | 3027 | 29 |

### Group: ArtComp (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtDim (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtEmp (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtEmp | 1959 | 51 |

### Group: ArtEnt (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtLng (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtMerc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ArtMerc | 6 | 25 |

### Group: ArtProp (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtPsion (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtRef (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtSubst (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtUnid (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ArtUnidWeb (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Artigos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Artigos | 2721 | 126 |

### Group: Avaliacoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Avaliacoes | 39 | 16 |

### Group: Bancos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Bancos | 25 | 15 |

### Group: CCO (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CCO | 34920 | 38 |

### Group: CCOLIQ (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CCOLIQ | 56586 | 9 |

### Group: CTB (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CTB | 23765 | 14 |

### Group: Carteiras (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Carteiras | 10 | 13 |

### Group: Cartoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Chats (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Chats | 37 | 14 |

### Group: Classificacoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Classificadores (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Comissoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ComissoesPeriodos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: CondPag (1 tables)

| Table | Rows | Cols |
|---|---|---|
| CondPag | 15 | 16 |

### Group: Consumos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ContCred (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ContCred | 4 | 15 |

### Group: Contactos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Contactos | 30 | 9 |

### Group: DocCart (1 tables)

| Table | Rows | Cols |
|---|---|---|
| DocCart | 25 | 4 |

### Group: Entidades (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Entidades | 1955 | 119 |

### Group: EntidadesRelacoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| EntidadesRelacoes | 1898 | 8 |

### Group: Eventos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Expedicoes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Expedicoes | 21 | 11 |

### Group: FO (1 tables)

| Table | Rows | Cols |
|---|---|---|
| FO | 9630 | 69 |

### Group: FOF (1 tables)

| Table | Rows | Cols |
|---|---|---|
| FOF | 2 | 65 |

### Group: Fields (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Fields | 370 | 11 |

### Group: GrTam (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: GrpDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| GrpDoc | 21 | 12 |

### Group: GrpDocTp (1 tables)

| Table | Rows | Cols |
|---|---|---|
| GrpDocTp | 67 | 4 |

### Group: Hardware (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Hardware | 2 | 8 |

### Group: Horarios (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ImageRead (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ImageRead | 6 | 4 |

### Group: Impressoras (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Impressoras | 5 | 12 |

### Group: LangFields (1 tables)

| Table | Rows | Cols |
|---|---|---|
| LangFields | 597 | 11 |

### Group: Language (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Language | 2 | 8 |

### Group: Licencas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Licencas | 32 | 18 |

### Group: LinDOc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| LinDOc001_GrFamilia | 57820 | 2 |

### Group: Linguas (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Lotes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Lotes | 1 | 15 |

### Group: Meses (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: ModoPag (1 tables)

| Table | Rows | Cols |
|---|---|---|
| ModoPag | 1 | 13 |

### Group: ModosEntrega (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Moeda (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Moeda | 3 | 18 |

### Group: MultiDim (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Numeradores (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Numeradores | 47 | 12 |

### Group: Operacoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: PckTransactions (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Pessoal (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Planos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: PortalBanners (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalBanners | 136 | 10 |

### Group: PortalContacts (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalContacts | 2 | 22 |

### Group: PortalDestak (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: PortalDetails (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalDetails | 74 | 14 |

### Group: PortalDetailsGeral (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalDetailsGeral | 8 | 13 |

### Group: PortalFields (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalFields | 8 | 11 |

### Group: PortalLangFields (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalLangFields | 24 | 11 |

### Group: PortalLanguage (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalLanguage | 2 | 8 |

### Group: PortalMenu (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalMenu | 6 | 10 |

### Group: PortalMenuEng (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalMenuEng | 5 | 10 |

### Group: PortalNews (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalNews | 19 | 11 |

### Group: PortalPartners (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalPartners | 4 | 11 |

### Group: PortalProdDetails (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalProdDetails | 32 | 19 |

### Group: PortalProdFields (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalProdFields | 32 | 12 |

### Group: PortalSubMenu (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalSubMenu | 11 | 10 |

### Group: PortalSubMenuEng (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalSubMenuEng | 11 | 11 |

### Group: PortalSubSubjects (1 tables)

| Table | Rows | Cols |
|---|---|---|
| PortalSubSubjects | 3 | 11 |

### Group: PortalTestimony (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: PosOperacoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Postos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Postos | 13 | 47 |

### Group: Priority (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Priority | 3 | 10 |

### Group: PsionCab (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: PsionLin (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: RegTpIVA (1 tables)

| Table | Rows | Cols |
|---|---|---|
| RegTpIVA | 19 | 6 |

### Group: RegimesIVA (1 tables)

| Table | Rows | Cols |
|---|---|---|
| RegimesIVA | 13 | 17 |

### Group: RequestTypes (1 tables)

| Table | Rows | Cols |
|---|---|---|
| RequestTypes | 5 | 9 |

### Group: Requests (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Requests | 22 | 25 |

### Group: Rotas (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: SNCFiles (1 tables)

| Table | Rows | Cols |
|---|---|---|
| SNCFiles | 12 | 5 |

### Group: SYSLOCK (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: SYSLOG (1 tables)

| Table | Rows | Cols |
|---|---|---|
| SYSLOG | 6290 | 10 |

### Group: SYSProfiles (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: SYSProfilesPerm (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Seccoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Sessoes (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Severity (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Severity | 3 | 10 |

### Group: Software (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Software | 16 | 8 |

### Group: Status (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Status | 6 | 8 |

### Group: TabClassif (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Taras (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Tasks (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Tasks | 13 | 20 |

### Group: Telefone (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Telefone | 105 | 5 |

### Group: TempX (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TempX | 94 | 9 |

### Group: Tempos (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TiposComissao (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TiposContas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposContas | 6 | 13 |

### Group: TiposDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDoc | 35 | 64 |

### Group: TiposDocAT (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocAT | 24 | 9 |

### Group: TiposDocCCO (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocCCO | 37 | 45 |

### Group: TiposDocCtb (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocCtb | 9 | 22 |

### Group: TiposDocLin (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocLin | 110 | 4 |

### Group: TiposDocLinCtb (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocLinCtb | 10 | 16 |

### Group: TiposDocPst (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposDocPst | 214 | 11 |

### Group: TiposEmbalagem (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TiposInt (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposInt | 16 | 28 |

### Group: TiposIntL (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposIntL | 24 | 13 |

### Group: TiposIva (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposIva | 4 | 14 |

### Group: TiposLin (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposLin | 46 | 64 |

### Group: TiposLinSTC (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposLinSTC | 43 | 34 |

### Group: TiposSerieNum (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TiposSerieNum | 124 | 7 |

### Group: TiposSerieTpDoc (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpCCO (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpConf (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpEtiq (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TmpEtiq | 2504 | 9 |

### Group: TmpInt (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TmpInt | 8 | 77 |

### Group: TmpIntAn (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpMultiDim (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpObras (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpStc (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TmpX (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TpContactos (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpContactos | 1 | 13 |

### Group: TpContas (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TpDocATSerie (1 tables)

| Table | Rows | Cols |
|---|---|---|
| TpDocATSerie | 8 | 4 |

### Group: TpDocML (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: TpEnt (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: Unidades (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Unidades | 2 | 17 |

### Group: Vendedores (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Vendedores | 11 | 24 |

### Group: Zonas (1 tables)

| Table | Rows | Cols |
|---|---|---|
| Zonas | 1 | 13 |

### Group: _a (1 tables)

| Table | Rows | Cols |
|---|---|---|
| _a | 275 | 1 |

### Group: image (1 tables)

| Table | Rows | Cols |
|---|---|---|
| image | 13 | 4 |

### Group: sys (1 tables)

| Table | Rows | Cols |
|---|---|---|
| sys99n | 8 | 58 |

### Group: tmporder (1 tables)

| Table | Rows | Cols |
|---|---|---|

### Group: tmpsession (1 tables)

| Table | Rows | Cols |
|---|---|---|
| tmpsession | 11 | 8 |

## SYS Tables — Configuration & Lookup

The `SYS` prefix tables are internal ERP configuration tables (dbSoft).
They store system parameters, numbering sequences, permissions, etc.

| Table | Rows | Purpose (inferred) |
|---|---|---|
| SYS00 | 90 | Company / installation config |
| SYS01 | 196 | Users / operators |
| SYS02 | 1409 | User permissions |
| SYS03 | 8 | Workstations / terminals |
| SYS07 | 734 | Audit log / activity log |
| SYS08 | 138 | Document series config |
| SYS98 | 211 | System events / counters |
| SYS99 | 1510 | General parameter store |

## DOClinic — Medical Clinic Specifics

DOClinic has additional tables not present in DevDB:

| Table | Rows | Cols |
|---|---|---|
| A | 101 | 38 |
| A_DadosCredenciaisEspeciais | 0 | 15 |
| A_DadosCredenciaisEspeciais_Linhas | 0 | 7 |
| ArtMedico | 37 | 7 |
| ArtMercHon | 242 | 19 |
| B | 204 | 1 |
| CRM11 | 4 | 9 |
| CRM12 | 12 | 9 |
| CRM13 | 24 | 4 |
| CRM14 | 10 | 4 |
| Carimbos | 17 | 9 |
| CartEnt | 0 | 4 |
| ComissoesTpEnt | 0 | 6 |
| ConfigResults | 5 | 31 |
| Cred | 6584 | 2 |
| CredenciaisSNS | 113560 | 12 |
| Declaracoes | 9118 | 5 |
| Devolucoes | 0 | 14 |
| Diagnosticos | 1200 | 14 |
| DiagnosticosSnomed | 0 | 13 |
| Dias | 799 | 7 |
| Doc00120260106 | 1163 | 88 |
| DocCPart | 5 | 4 |
| ERPalavrasVox | 2 | 8 |
| ESP_EstadoEnvios | 0 | 7 |
| ESP_LOG | 0 | 7 |
| ESP_RegistoDeMensagensESP | 0 | 5 |
| EmpresaConvencoes | 59 | 7 |
| EmpresaSeries | 0 | 4 |
| EmpresasMeiosLiquidacao | 0 | 4 |
| EntidadesBkp | 12401 | 149 |
| EntidadesLP | 11800 | 142 |
| EntidadesSeries | 23 | 4 |
| EntidadesTPA | 0 | 15 |
| Especialidades | 29 | 12 |
| Estados | 103 | 23 |
| Familias | 0 | 10 |
| GrpArtigos | 47 | 25 |
| GrpRec | 122 | 4 |
| ImpressoesEnvios | 0 | 6 |
| KK | 11 | 25 |
| LinDoc001_Delete | 0 | 65 |
| LinDoc002_Delete | 0 | 28 |
| ListaLP_SNS | 6916 | 3 |
| Locais | 3 | 12 |
| LocaisPrescricaoComissoes | 0 | 4 |
| MovCCOCart | 0 | 4 |
| NHParticulares | 525 | 1 |
| OrigensEntidades | 8 | 4 |
| PagamentosTPA | 1 | 12 |
| Paineis | 25 | 8 |
| PaineisTpPedidosExtras | 141 | 3 |
| PedidosRecolha | 0 | 12 |
| Prescritores | 8937 | 27 |
| PrescritoresLocais | 19391 | 5 |
| RefSIBSHist | 44 | 2 |
| Regras | 704 | 25 |
| Reservas | 9542 | 167 |
| ReservasCredenciais | 0 | 7 |
| ReservasEnvios | 9071 | 16 |
| ReservasEstados | 71755 | 8 |
| ReservasHist | 0 | 11 |
| ReservasPedidos | 0 | 13 |
| ReservasServicos | 9575 | 13 |
| Reservas_delete | 0 | 169 |
| SNS_Devolucoes | 0 | 14 |
| SNS_LP | 6892 | 4 |
| SNS_ListaErros | 23 | 5 |
| SYS04 | 0 | 2 |
| SYS40 | 0 | 5 |
| SYS97 | 0 | 5 |
| SYSDefaults | 9 | 11 |
| SYSER01 | 25 | 19 |
| SYSER02 | 56 | 6 |
| SYSER03 | 6 | 3 |
| SmsQueue | 0 | 13 |
| TMP_ListaLP_SNS | 0 | 12 |
| TextoModificador | 63 | 8 |
| TimeService_LogX | 0 | 4 |
| TipoTerc | 289 | 2 |
| Titulos | 21 | 15 |
| Tmp | 12 | 25 |
| TmpAgenda | 0 | 6 |
| TmpCTB | 0 | 1 |
| TmpEncFact | 0 | 9 |
| TmpReservas | 0 | 3 |
| TpArtigos | 4 | 15 |
| WebLidos | 69779 | 8 |
| WebLogin | 13 | 18 |
| WebLoginEntidades | 26 | 16 |
| WebLoginEntidades_TMP | 35 | 3 |
| WebMensagens | 12 | 23 |
| WebTipoMensagens | 3 | 4 |
| WorkMail | 8 | 15 |
| WorkMailAnexos | 7 | 6 |
| _A_ESP_ResultadoEnvioSync | 0 | 8 |
| sysdiagrams | 0 | 5 |

## Inferred Business Rules

### Sales Analytics
- **Sales filter**: `Doc001.TipoDoc = 1` (invoices/sales)
- **Date filter**: `Doc001.Data >= 'YYYY-01-01' AND Doc001.Data < 'YYYY+1-01-01'`
- **Total sales**: `SUM(Doc001.Total)` or `SUM(LinDoc001.Valor)` at line level
- **By article**: join LinDoc001 → Artigos on `ChaveProd = Artigos.Chave`
- **By family**: self-join Artigos on `Artigos.ChPai = parent.Chave`

### DevDB 2026 Sales Benchmark (TipoDoc=1)
- Total: €78,318.87 across 83 documents
- Top family: Software dbSoft (€12,618) and Serviço dbSoft (€12,445)

### DOClinic 2026 Sales Benchmark (TipoDoc=1)
- Total: €348,538.41 across 4,145 documents
- Top article: Consulta de Ortopedia - 1ª Consulta (€34,398 / 406 consultations)

### Archive/Soft-delete Pattern
- Deleted records moved to `*_Delete` tables (e.g. `Doc001_Delete`, `LinDoc001_Delete`)
- Never physically deleted from main tables

### No FK Constraints
- All referential integrity enforced at application layer (dbSoft ERP)
- Relationships inferred from column naming conventions
- `Chave` = universal surrogate PK (bigint) across all master tables
- `Ch*` prefix columns = FK references (e.g. `ChaveProd`, `ChPai`, `Chpai`)

### Portuguese Fiscal Compliance
- `ATCUD` — unique document code required by Portuguese Tax Authority (AT)
- `CodigoAT` — AT validation code
- `RegIVA` — VAT regime
- `Certificacao` / `CertificacaoEstado` — digital certification status
