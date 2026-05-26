# Database Schema Reference — ForumSI / dbSoft ERP

Generated from live SQL Server 2025 at `149.86.232.229:1033`.
No FK constraints are defined in the DB — all relationships are **logical** (enforced by application).

## Databases

| Database | Tables | Views | Purpose |
|---|---|---|---|
| DevDB | 228 | 12 | ForumSI IT company — software sales, hardware, support |
| DOClinic | 195 | 49 | Medical clinic — consultations, exams, healthcare |
| ForumSI | 241 | 12 | Mirror of DevDB (same schema, same data volume) |
| OpenInnovation | ~200 | — | Innovation entity — minimal data |

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

### TipoDoc — Document Types

## DevDB — Full Table Inventory

Total: **228 tables**, 12 views

### Group: SYS (33 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYS00 | 90 | 11 | Chave |
| SYS01 | 196 | 12 | Chave |
| SYS01_Catalogo | 18 | 12 | Chave |
| SYS02 | 1409 | 24 | — |
| SYS03 | 8 | 36 | Chave |
| SYS05 | 0 | 4 | Chave |
| SYS07 | 734 | 36 | — |
| SYS08 | 138 | 3 | Chave |
| SYS09 | 0 | 10 | Chave, Tipo, Estado |
| SYS10 | 5 | 8 | Chave, Estado |
| SYS11 | 14 | 11 | Chave, Origem, Destino |
| SYS12 | 5 | 7 | Chave, Destino |
| SYS13 | 15 | 6 | Chave, Posto |
| SYS14 | 1 | 7 | Chave |
| SYS15 | 0 | 7 | Chave |
| SYS16 | 0 | 4 | Chave |
| SYS17 | 0 | 5 | Chave, Origem, Destino |
| SYS20 | 0 | 4 | Tipo, Estado |
| SYS21 | 0 | 6 | Tipo, Origem, Destino |
| SYS22 | 0 | 7 | Tipo, Destino |
| SYS23 | 1 | 7 | Chave, Tipo, Posto |
| SYS24 | 0 | 15 | Chave |
| SYS60 | 5 | 24 | Chave |
| SYS61 | 24 | 8 | Chave |
| SYS62 | 0 | 4 | Chave |
| SYS63 | 13 | 6 | Chave |
| SYS64 | 3 | 3 | Chave |
| SYS65 | 0 | 14 | Chave |
| SYS70 | 0 | 21 | Chave |
| SYS81 | 0 | 5 | Chave |
| SYS96 | 0 | 6 | Chave |
| SYS98 | 211 | 5 | OP, Chave |
| SYS99 | 1510 | 58 | — |

### Group: CRM (19 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CRM_99 | 43 | 17 | Chave |
| CRM_Anexos | 2277 | 12 | — |
| CRM_Assinaturas | 0 | 9 | Chave |
| CRM_Atividades | 160 | 26 | Chave |
| CRM_AtividadesEstados | 321 | 7 | — |
| CRM_Comunicacoes | 18 | 11 | — |
| CRM_Emails | 3438 | 16 | Chave |
| CRM_Enderecos | 3536 | 10 | — |
| CRM_Equipamentos | 0 | 11 | Chave |
| CRM_Estados | 16 | 10 | Chave |
| CRM_GruposProcessos | 3 | 8 | — |
| CRM_Inbox | 7 | 23 | — |
| CRM_ProcessosAtividades | 70 | 4 | Chave |
| CRM_RelGruposProcessos | 0 | 6 | — |
| CRM_TipoAtividadesProcessos | 36 | 19 | Chave |
| CRM_Transicoes | 90 | 3 | Chave |
| CRM_Utilizadores | 7 | 13 | Chave |
| CRM_UtilizadoresEquipas | 0 | 8 | Chave |
| CRM_UtilizadoresInbox | 13 | 7 | Chave |

### Group: IO (7 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| IO_Inbox | 0 | 12 | ID |
| IO_InboxArquivo | 0 | 11 | ID |
| IO_InboxData | 0 | 2 | ID |
| IO_MsgData | 0 | 2 | ID |
| IO_Outbox | 0 | 7 | ID |
| IO_SentItems | 0 | 6 | ID |
| IO_Users | 0 | 5 | UserName, Contexto |

### Group: ATR (5 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ATR_Atributos | 795 | 12 | Chave |
| ATR_ContextosTiposAtributos | 30 | 11 | Chave |
| ATR_Listas | 4 | 6 | Chave |
| ATR_RelContextosAtributos | 40 | 11 | Chave |
| ATR_TiposDados | 16 | 12 | Chave |

### Group: Pos (4 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Pos03 | 0 | 15 | Chave |
| Pos51 | 0 | 4 | — |
| Pos52 | 0 | 6 | — |
| Pos70 | 0 | 46 | Chave |

### Group: Doc (3 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Doc001 | 21286 | 80 | Chave |
| Doc001_Delete | 603 | 80 | — |
| Doc005 | 3 | 3 | Chave |

### Group: LinDoc (3 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| LinDoc001 | 63769 | 84 | Chave |
| LinDoc002 | 0 | 33 | Chave |
| LinDoc003 | 0 | 10 | Chave |

### Group: LinPlan (2 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| LinPlan001 | 0 | 24 | Chave |
| LinPlan002 | 0 | 9 | Chave |

### Group: Lindoc (2 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Lindoc001_Delete | 1939 | 84 | — |
| Lindoc005 | 16 | 4 | Chave |

### Group: Plan (2 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Plan001 | 0 | 18 | Chave |
| Plan002 | 0 | 15 | Chave |

### Group: AVencimento (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AVencimento | 3 | 17 | Chave |

### Group: Acessos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Acessos | 3 | 9 | — |

### Group: Anexos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Anexos | 12 | 20 | Chave |

### Group: AnexosCat (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosCat | 0 | 3 | Chave |

### Group: AnexosGrpDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosGrpDoc | 5 | 9 | Chave |

### Group: AnexosGrpDocTp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosGrpDocTp | 15 | 4 | Chave |

### Group: AnexosIndexantes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosIndexantes | 0 | 9 | Chave |

### Group: AnexosPalavrasChave (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosPalavrasChave | 11 | 4 | Chave |

### Group: AnexosTiposDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosTiposDoc | 57 | 10 | Chave |

### Group: AnexosTiposDocIndexantes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosTiposDocIndexantes | 0 | 3 | Chave |

### Group: ArtArm (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtArm | 3026 | 29 | Chave |

### Group: ArtComp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtComp | 0 | 8 | Chave |

### Group: ArtDim (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtDim | 0 | 4 | Chave |

### Group: ArtEmp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtEmp | 1958 | 51 | Chave |

### Group: ArtEnt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtEnt | 0 | 3 | chave |

### Group: ArtLng (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtLng | 0 | 4 | Chave |

### Group: ArtMerc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtMerc | 6 | 25 | Chave |

### Group: ArtProp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtProp | 0 | 26 | Chave |

### Group: ArtPsion (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtPsion | 0 | 5 | Chave |

### Group: ArtRef (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtRef | 0 | 6 | Chave |

### Group: ArtSubst (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtSubst | 0 | 3 | Chave |

### Group: ArtUnid (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtUnid | 0 | 5 | Chave |

### Group: ArtUnidWeb (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtUnidWeb | 0 | 4 | Chave |

### Group: Artigos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Artigos | 2720 | 126 | Chave |

### Group: Avaliacoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Avaliacoes | 39 | 16 | Chave |

### Group: Bancos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Bancos | 25 | 15 | Chave |

### Group: CCO (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CCO | 34906 | 38 | Chave |

### Group: CCOLIQ (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CCOLIQ | 56566 | 9 | Chave |

### Group: CTB (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CTB | 23765 | 14 | — |

### Group: Carteiras (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Carteiras | 10 | 13 | Chave |

### Group: Cartoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Cartoes | 0 | 13 | Chave |

### Group: Chats (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Chats | 37 | 14 | Chave |

### Group: Classificacoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Classificacoes | 0 | 13 | Chave |

### Group: Classificadores (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Classificadores | 0 | 17 | Chave |

### Group: Comissoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Comissoes | 0 | 7 | Chave |

### Group: ComissoesPeriodos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ComissoesPeriodos | 0 | 14 | Chave |

### Group: CondPag (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CondPag | 15 | 16 | Chave |

### Group: Consumos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Consumos | 0 | 40 | Chave |

### Group: ContCred (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ContCred | 4 | 15 | Chave |

### Group: Contactos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Contactos | 30 | 9 | Chave |

### Group: DocCart (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| DocCart | 25 | 4 | Chave |

### Group: Entidades (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Entidades | 1955 | 119 | Chave |

### Group: EntidadesRelacoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| EntidadesRelacoes | 1898 | 8 | — |

### Group: Eventos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Eventos | 0 | 7 | Chave |

### Group: Expedicoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Expedicoes | 21 | 11 | Chave |

### Group: FO (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| FO | 9630 | 69 | Chave |

### Group: Fields (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Fields | 370 | 11 | Chave |

### Group: GrTam (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| GrTam | 0 | 11 | Chave |

### Group: GrpDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| GrpDoc | 21 | 12 | Chave |

### Group: GrpDocTp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| GrpDocTp | 67 | 4 | Chave |

### Group: Hardware (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Hardware | 2 | 8 | Chave |

### Group: Horarios (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Horarios | 0 | 14 | Chave |

### Group: ImageRead (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ImageRead | 6 | 4 | — |

### Group: Impressoras (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Impressoras | 5 | 12 | Chave |

### Group: LangFields (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| LangFields | 597 | 11 | Chave |

### Group: Language (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Language | 2 | 8 | Chave |

### Group: Licencas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Licencas | 32 | 18 | Chave |

### Group: LinDOc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| LinDOc001_GrFamilia | 57820 | 2 | — |

### Group: Linguas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Linguas | 0 | 12 | Chave |

### Group: Lotes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Lotes | 1 | 15 | Chave |

### Group: ModoPag (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ModoPag | 1 | 13 | Chave |

### Group: ModosEntrega (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ModosEntrega | 0 | 12 | Chave |

### Group: Moeda (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Moeda | 3 | 18 | Chave |

### Group: MultiDim (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| MultiDim | 0 | 14 | Chave |

### Group: Numeradores (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Numeradores | 47 | 12 | Chave |

### Group: Operacoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Operacoes | 0 | 27 | Chave |

### Group: PckTransactions (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PckTransactions | 0 | 5 | Id, Chave, Tabela |

### Group: Pessoal (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Pessoal | 0 | 21 | Chave |

### Group: Planos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Planos | 0 | 19 | Chave |

### Group: PortalBanners (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalBanners | 136 | 10 | Chave |

### Group: PortalContacts (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalContacts | 2 | 22 | Chave |

### Group: PortalDestak (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalDestak | 0 | 11 | Chave |

### Group: PortalDetails (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalDetails | 74 | 14 | Chave |

### Group: PortalDetailsGeral (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalDetailsGeral | 8 | 13 | Chave |

### Group: PortalFields (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalFields | 8 | 11 | Chave |

### Group: PortalLangFields (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalLangFields | 24 | 11 | Chave |

### Group: PortalLanguage (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalLanguage | 2 | 8 | Chave |

### Group: PortalMenu (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalMenu | 6 | 10 | Chave |

### Group: PortalMenuEng (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalMenuEng | 5 | 10 | Chave |

### Group: PortalNews (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalNews | 19 | 11 | Chave |

### Group: PortalPartners (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalPartners | 4 | 11 | Chave |

### Group: PortalProdDetails (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalProdDetails | 32 | 19 | Chave |

### Group: PortalProdFields (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalProdFields | 32 | 12 | Chave |

### Group: PortalSubMenu (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalSubMenu | 11 | 10 | Chave |

### Group: PortalSubMenuEng (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalSubMenuEng | 11 | 11 | Chave |

### Group: PortalSubSubjects (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalSubSubjects | 3 | 11 | Chave |

### Group: PortalTestimony (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalTestimony | 0 | 11 | Chave |

### Group: PosOperacoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PosOperacoes | 0 | 11 | Chave |

### Group: Postos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Postos | 13 | 47 | Chave |

### Group: Priority (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Priority | 3 | 10 | Chave |

### Group: PsionCab (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PsionCab | 0 | 7 | — |

### Group: PsionLin (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PsionLin | 0 | 9 | — |

### Group: RegTpIVA (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| RegTpIVA | 19 | 6 | Chave |

### Group: RegimesIVA (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| RegimesIVA | 13 | 17 | Chave |

### Group: RequestTypes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| RequestTypes | 5 | 9 | Chave |

### Group: Requests (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Requests | 22 | 25 | Chave |

### Group: Rotas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Rotas | 0 | 17 | Chave |

### Group: SNCFiles (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SNCFiles | 12 | 5 | — |

### Group: SYSLOCK (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYSLOCK | 0 | 37 | — |

### Group: SYSLOG (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYSLOG | 6260 | 10 | ChaveReg |

### Group: SYSProfiles (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYSProfiles | 0 | 19 | Chave |

### Group: SYSProfilesPerm (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYSProfilesPerm | 0 | 4 | Chave |

### Group: Seccoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Seccoes | 0 | 12 | Chave |

### Group: Sessoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Sessoes | 0 | 7 | Chave |

### Group: Severity (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Severity | 3 | 10 | Chave |

### Group: Software (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Software | 16 | 8 | Chave |

### Group: Status (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Status | 6 | 8 | Chave |

### Group: TabClassif (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TabClassif | 0 | 8 | Chave |

### Group: Taras (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Taras | 0 | 10 | Chave |

### Group: Tasks (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Tasks | 13 | 20 | Chave |

### Group: Telefone (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Telefone | 105 | 5 | — |

### Group: Tempos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Tempos2 | 0 | 14 | Chave |

### Group: TiposComissao (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposComissao | 0 | 14 | Chave |

### Group: TiposContas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposContas | 6 | 13 | Chave |

### Group: TiposDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDoc | 35 | 64 | Chave |

### Group: TiposDocAT (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocAT | 24 | 9 | Chave |

### Group: TiposDocCCO (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocCCO | 37 | 45 | Chave |

### Group: TiposDocCtb (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocCtb | 9 | 22 | Chave |

### Group: TiposDocLin (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocLin | 110 | 4 | Chave |

### Group: TiposDocLinCtb (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocLinCtb | 10 | 16 | Chave |

### Group: TiposDocPst (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocPst | 214 | 11 | Chave |

### Group: TiposEmbalagem (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposEmbalagem | 0 | 14 | Chave |

### Group: TiposInt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposInt | 16 | 28 | Chave |

### Group: TiposIntL (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposIntL | 24 | 13 | Chave |

### Group: TiposIva (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposIva | 4 | 14 | Chave |

### Group: TiposLin (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposLin | 46 | 64 | Chave |

### Group: TiposLinSTC (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposLinSTC | 43 | 34 | Chave |

### Group: TiposSerieNum (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposSerieNum | 124 | 7 | Chave |

### Group: TiposSerieTpDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposSerieTpDoc | 0 | 4 | Chave |

### Group: TmpCCO (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpCCO | 0 | 16 | — |

### Group: TmpConf (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpConf | 0 | 17 | — |

### Group: TmpEtiq (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpEtiq | 2504 | 9 | — |

### Group: TmpInt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpInt | 8 | 77 | — |

### Group: TmpIntAn (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpIntAn | 0 | 5 | — |

### Group: TmpMultiDim (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpMultiDim | 0 | 11 | — |

### Group: TmpObras (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpObras | 0 | 13 | — |

### Group: TpContactos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpContactos | 1 | 13 | Chave |

### Group: TpContas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpContas | 0 | 7 | — |

### Group: TpDocATSerie (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpDocATSerie | 8 | 4 | Chave |

### Group: TpDocML (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpDocML | 0 | 3 | Chave |

### Group: TpEnt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpEnt | 0 | 13 | Chave |

### Group: Unidades (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Unidades | 2 | 17 | Chave |

### Group: Vendedores (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Vendedores | 11 | 24 | Chave |

### Group: Zonas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Zonas | 1 | 13 | Chave |

### Group: image (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| image | 13 | 4 | — |

### Group: sys (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| sys99n | 8 | 58 | — |

### Group: tmporder (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| tmporder | 0 | 8 | — |

### Group: tmpsession (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| tmpsession | 11 | 8 | chave |

## DOClinic — Full Table Inventory

Total: **195 tables**, 49 views

### Group: SYS (25 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYS00 | 159 | 11 | Chave |
| SYS01 | 403 | 10 | — |
| SYS02 | 3414 | 25 | — |
| SYS03 | 15 | 25 | Chave |
| SYS04 | 0 | 2 | — |
| SYS05 | 2 | 4 | Chave |
| SYS07 | 1565 | 38 | — |
| SYS08 | 210 | 3 | — |
| SYS09 | 0 | 10 | — |
| SYS10 | 0 | 7 | — |
| SYS11 | 0 | 11 | — |
| SYS12 | 0 | 7 | — |
| SYS13 | 0 | 7 | Chave |
| SYS40 | 0 | 5 | — |
| SYS60 | 11 | 22 | Chave |
| SYS61 | 1 | 9 | Chave |
| SYS62 | 1 | 4 | Chave |
| SYS63 | 4 | 6 | Chave |
| SYS64 | 0 | 3 | Chave |
| SYS70 | 2 | 21 | Chave |
| SYS81 | 2 | 4 | — |
| SYS96 | 0 | 6 | Chave |
| SYS97 | 0 | 5 | — |
| SYS98 | 475 | 16 | — |
| SYS99 | 3891 | 60 | — |

### Group: CRM (5 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CRM11 | 4 | 9 | Chave |
| CRM12 | 12 | 9 | Chave |
| CRM13 | 24 | 4 | Chave |
| CRM14 | 10 | 4 | Chave |
| CRM_Inbox | 1 | 20 | — |

### Group: LinDoc (4 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| LinDoc001 | 6739 | 67 | Chave |
| LinDoc001_Delete | 0 | 65 | Chave |
| LinDoc002 | 0 | 28 | Chave |
| LinDoc002_Delete | 0 | 28 | — |

### Group: A (3 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| A | 101 | 38 | — |
| A_DadosCredenciaisEspeciais | 0 | 15 | Chave |
| A_DadosCredenciaisEspeciais_Linhas | 0 | 7 | Chave |

### Group: Doc (3 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Doc001 | 5487 | 88 | Chave |
| Doc00120260106 | 1163 | 88 | — |
| Doc001_Delete | 0 | 85 | Chave |

### Group: ESP (3 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ESP_EstadoEnvios | 0 | 7 | Chave |
| ESP_LOG | 0 | 7 | Chave |
| ESP_RegistoDeMensagensESP | 0 | 5 | Chave |

### Group: SNS (3 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SNS_Devolucoes | 0 | 14 | — |
| SNS_LP | 6892 | 4 | — |
| SNS_ListaErros | 23 | 5 | — |

### Group: SYSER (3 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYSER01 | 25 | 19 | Chave |
| SYSER02 | 56 | 6 | Chave |
| SYSER03 | 6 | 3 | Chave |

### Group: Reservas (2 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Reservas | 9542 | 167 | Chave |
| Reservas_delete | 0 | 169 | Chave |

### Group: WebLoginEntidades (2 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| WebLoginEntidades | 26 | 16 | Chave |
| WebLoginEntidades_TMP | 35 | 3 | — |

### Group: Anexos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Anexos | 0 | 16 | Chave |

### Group: ArtArm (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtArm | 6 | 25 | Chave |

### Group: ArtComp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtComp | 1 | 6 | Chave |

### Group: ArtDim (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtDim | 0 | 4 | Chave |

### Group: ArtLng (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtLng | 0 | 5 | Chave |

### Group: ArtMedico (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtMedico | 37 | 7 | — |

### Group: ArtMerc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtMerc | 338 | 19 | Chave |

### Group: ArtMercHon (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtMercHon | 242 | 19 | — |

### Group: Artigos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Artigos | 191 | 101 | Chave |

### Group: B (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| B | 204 | 1 | — |

### Group: Bancos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Bancos | 12 | 15 | Chave |

### Group: CCO (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CCO | 5167 | 41 | Chave |

### Group: CCOLIQ (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CCOLIQ | 5166 | 9 | Chave |

### Group: CTB (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CTB | 0 | 14 | — |

### Group: Carimbos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Carimbos | 17 | 9 | Chave |

### Group: CartEnt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CartEnt | 0 | 4 | Chave |

### Group: Carteiras (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Carteiras | 10 | 13 | Chave |

### Group: Comissoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Comissoes | 0 | 19 | Chave |

### Group: ComissoesTpEnt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ComissoesTpEnt | 0 | 6 | Chave |

### Group: CondPag (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CondPag | 6 | 16 | Chave |

### Group: ConfigResults (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ConfigResults | 5 | 31 | Chave |

### Group: Consumos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Consumos | 0 | 40 | Chave |

### Group: ContCred (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ContCred | 0 | 15 | Chave |

### Group: Contactos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Contactos | 542 | 8 | Chave |

### Group: Cred (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Cred | 6584 | 2 | — |

### Group: CredenciaisSNS (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CredenciaisSNS | 113560 | 12 | — |

### Group: Declaracoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Declaracoes | 9118 | 5 | — |

### Group: Devolucoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Devolucoes | 0 | 14 | Chave |

### Group: Diagnosticos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Diagnosticos | 1200 | 14 | Chave |

### Group: DiagnosticosSnomed (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| DiagnosticosSnomed | 0 | 13 | Chave |

### Group: Dias (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Dias | 799 | 7 | Chave |

### Group: DocCPart (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| DocCPart | 5 | 4 | Chave |

### Group: DocCart (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| DocCart | 34 | 4 | Chave |

### Group: ERPalavrasVox (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ERPalavrasVox | 2 | 8 | Chave |

### Group: EmpresaConvencoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| EmpresaConvencoes | 59 | 7 | Chave |

### Group: EmpresaSeries (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| EmpresaSeries | 0 | 4 | Chave |

### Group: EmpresasMeiosLiquidacao (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| EmpresasMeiosLiquidacao | 0 | 4 | Chave |

### Group: Entidades (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Entidades | 28452 | 149 | Chave |

### Group: EntidadesBkp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| EntidadesBkp | 12401 | 149 | — |

### Group: EntidadesLP (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| EntidadesLP | 11800 | 142 | — |

### Group: EntidadesSeries (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| EntidadesSeries | 23 | 4 | — |

### Group: EntidadesTPA (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| EntidadesTPA | 0 | 15 | Chave |

### Group: Especialidades (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Especialidades | 29 | 12 | Chave |

### Group: Estados (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Estados | 103 | 23 | Chave |

### Group: Expedicoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Expedicoes | 2 | 11 | Chave |

### Group: FO (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| FO | 1 | 118 | Chave |

### Group: Familias (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Familias | 0 | 10 | — |

### Group: GrTam (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| GrTam | 0 | 11 | Chave |

### Group: GrpArtigos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| GrpArtigos | 47 | 25 | — |

### Group: GrpDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| GrpDoc | 13 | 11 | Chave |

### Group: GrpDocTp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| GrpDocTp | 48 | 3 | Chave |

### Group: GrpRec (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| GrpRec | 122 | 4 | — |

### Group: ImpressoesEnvios (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ImpressoesEnvios | 0 | 6 | Chave |

### Group: Impressoras (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Impressoras | 14 | 12 | Chave |

### Group: KK (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| KK | 11 | 25 | — |

### Group: Linguas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Linguas | 0 | 12 | Chave |

### Group: ListaLP (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ListaLP_SNS | 6916 | 3 | — |

### Group: Locais (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Locais | 3 | 12 | Chave |

### Group: LocaisPrescricaoComissoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| LocaisPrescricaoComissoes | 0 | 4 | Chave |

### Group: Lotes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Lotes | 1 | 13 | Chave |

### Group: ModoPag (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ModoPag | 2 | 13 | Chave |

### Group: Moeda (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Moeda | 2 | 18 | Chave |

### Group: MovCCOCart (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| MovCCOCart | 0 | 4 | Chave |

### Group: MultiDim (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| MultiDim | 0 | 14 | Chave |

### Group: NHParticulares (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| NHParticulares | 525 | 1 | — |

### Group: Numeradores (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Numeradores | 53 | 12 | Chave |

### Group: Operacoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Operacoes | 33 | 15 | Chave |

### Group: OrigensEntidades (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| OrigensEntidades | 8 | 4 | Chave |

### Group: PagamentosTPA (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PagamentosTPA | 1 | 12 | Chave |

### Group: Paineis (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Paineis | 25 | 8 | Chave |

### Group: PaineisTpPedidosExtras (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PaineisTpPedidosExtras | 141 | 3 | Chave |

### Group: PedidosRecolha (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PedidosRecolha | 0 | 12 | Chave |

### Group: Pessoal (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Pessoal | 1 | 21 | Chave |

### Group: Pos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Pos03 | 0 | 15 | Chave |

### Group: Postos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Postos | 48 | 50 | Chave |

### Group: Prescritores (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Prescritores | 8937 | 27 | Chave |

### Group: PrescritoresLocais (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PrescritoresLocais | 19391 | 5 | Chave |

### Group: RefSIBSHist (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| RefSIBSHist | 44 | 2 | — |

### Group: RegTpIVA (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| RegTpIVA | 16 | 5 | Chave |

### Group: RegimesIVA (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| RegimesIVA | 4 | 16 | Chave |

### Group: Regras (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Regras | 704 | 25 | Chave |

### Group: ReservasCredenciais (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ReservasCredenciais | 0 | 7 | — |

### Group: ReservasEnvios (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ReservasEnvios | 9071 | 16 | Chave |

### Group: ReservasEstados (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ReservasEstados | 71755 | 8 | Chave |

### Group: ReservasHist (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ReservasHist | 0 | 11 | Chave |

### Group: ReservasPedidos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ReservasPedidos | 0 | 13 | Chave |

### Group: ReservasServicos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ReservasServicos | 9575 | 13 | Chave |

### Group: Rotas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Rotas | 1 | 17 | Chave |

### Group: SYSDefaults (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYSDefaults | 9 | 11 | — |

### Group: SYSLOCK (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYSLOCK | 0 | 37 | — |

### Group: SYSLOG (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYSLOG | 32988 | 10 | — |

### Group: Seccoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Seccoes | 15 | 12 | Chave |

### Group: Sessoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Sessoes | 0 | 15 | Chave |

### Group: SmsQueue (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SmsQueue | 0 | 13 | Chave |

### Group: TMP (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TMP_ListaLP_SNS | 0 | 12 | — |

### Group: TextoModificador (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TextoModificador | 63 | 8 | — |

### Group: TimeService (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TimeService_LogX | 0 | 4 | — |

### Group: TipoTerc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TipoTerc | 289 | 2 | — |

### Group: TiposContas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposContas | 4 | 13 | Chave |

### Group: TiposDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDoc | 28 | 57 | Chave |

### Group: TiposDocAT (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocAT | 21 | 9 | Chave |

### Group: TiposDocCCO (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocCCO | 42 | 44 | Chave |

### Group: TiposDocCtb (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocCtb | 18 | 23 | Chave |

### Group: TiposDocLin (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocLin | 64 | 4 | Chave |

### Group: TiposDocLinCtb (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocLinCtb | 14 | 16 | Chave |

### Group: TiposDocPst (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocPst | 240 | 11 | Chave |

### Group: TiposInt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposInt | 12 | 27 | Chave |

### Group: TiposIntL (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposIntL | 78 | 13 | Chave |

### Group: TiposIva (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposIva | 5 | 14 | Chave |

### Group: TiposLin (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposLin | 36 | 60 | Chave |

### Group: TiposLinSTC (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposLinSTC | 11 | 34 | Chave |

### Group: TiposSerieNum (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposSerieNum | 126 | 5 | — |

### Group: TiposSerieTpDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposSerieTpDoc | 3 | 4 | Chave |

### Group: Titulos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Titulos | 21 | 15 | — |

### Group: Tmp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Tmp | 12 | 25 | — |

### Group: TmpAgenda (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpAgenda | 0 | 6 | — |

### Group: TmpCCO (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpCCO | 0 | 16 | — |

### Group: TmpCTB (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpCTB | 0 | 1 | — |

### Group: TmpConf (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpConf | 0 | 16 | — |

### Group: TmpEncFact (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpEncFact | 0 | 9 | — |

### Group: TmpEtiq (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpEtiq | 0 | 9 | — |

### Group: TmpInt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpInt | 0 | 71 | — |

### Group: TmpIntAn (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpIntAn | 0 | 5 | — |

### Group: TmpMultiDim (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpMultiDim | 0 | 11 | — |

### Group: TmpReservas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpReservas | 0 | 3 | — |

### Group: TpArtigos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpArtigos | 4 | 15 | Chave |

### Group: TpContactos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpContactos | 6 | 13 | Chave |

### Group: TpContas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpContas | 5 | 6 | Chave |

### Group: TpDocATSerie (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpDocATSerie | 14 | 4 | Chave |

### Group: TpDocML (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpDocML | 0 | 3 | Chave |

### Group: TpEnt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpEnt | 3 | 13 | Chave |

### Group: Unidades (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Unidades | 5 | 17 | Chave |

### Group: Vendedores (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Vendedores | 1 | 23 | Chave |

### Group: WebLidos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| WebLidos | 69779 | 8 | — |

### Group: WebLogin (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| WebLogin | 13 | 18 | Chave |

### Group: WebMensagens (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| WebMensagens | 12 | 23 | Chave |

### Group: WebTipoMensagens (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| WebTipoMensagens | 3 | 4 | Chave |

### Group: WorkMail (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| WorkMail | 8 | 15 | — |

### Group: WorkMailAnexos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| WorkMailAnexos | 7 | 6 | — |

### Group: Zonas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Zonas | 27 | 15 | Chave |

### Group: Other (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| _A_ESP_ResultadoEnvioSync | 0 | 8 | Chave |

### Group: sysdiagrams (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| sysdiagrams | 0 | 5 | diagram_id |

## ForumSI — Full Table Inventory

Total: **241 tables**, 12 views

### Group: SYS (34 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYS00 | 90 | 11 | Chave |
| SYS00Nova | 73 | 11 | — |
| SYS01 | 196 | 12 | Chave |
| SYS01_Catalogo | 18 | 12 | Chave |
| SYS02 | 1409 | 24 | — |
| SYS03 | 8 | 36 | Chave |
| SYS05 | 0 | 4 | Chave |
| SYS07 | 734 | 36 | — |
| SYS08 | 138 | 3 | Chave |
| SYS09 | 0 | 10 | Chave, Tipo, Estado |
| SYS10 | 5 | 8 | Chave, Estado |
| SYS11 | 14 | 11 | Chave, Origem, Destino |
| SYS12 | 5 | 7 | Chave, Destino |
| SYS13 | 15 | 6 | Chave, Posto |
| SYS14 | 1 | 7 | Chave |
| SYS15 | 0 | 7 | Chave |
| SYS16 | 0 | 4 | Chave |
| SYS17 | 0 | 5 | Chave, Origem, Destino |
| SYS20 | 0 | 4 | Tipo, Estado |
| SYS21 | 0 | 6 | Tipo, Origem, Destino |
| SYS22 | 0 | 7 | Tipo, Destino |
| SYS23 | 1 | 7 | Chave, Tipo, Posto |
| SYS24 | 0 | 15 | Chave |
| SYS60 | 5 | 24 | Chave |
| SYS61 | 24 | 8 | Chave |
| SYS62 | 0 | 4 | Chave |
| SYS63 | 13 | 6 | Chave |
| SYS64 | 3 | 3 | Chave |
| SYS65 | 0 | 14 | Chave |
| SYS70 | 0 | 21 | Chave |
| SYS81 | 0 | 5 | Chave |
| SYS96 | 0 | 6 | Chave |
| SYS98 | 211 | 5 | OP, Chave |
| SYS99 | 1510 | 58 | — |

### Group: CRM (19 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CRM_99 | 43 | 17 | Chave |
| CRM_Anexos | 2277 | 12 | — |
| CRM_Assinaturas | 0 | 9 | Chave |
| CRM_Atividades | 160 | 26 | Chave |
| CRM_AtividadesEstados | 321 | 7 | — |
| CRM_Comunicacoes | 18 | 11 | — |
| CRM_Emails | 3438 | 16 | Chave |
| CRM_Enderecos | 3536 | 10 | — |
| CRM_Equipamentos | 0 | 11 | Chave |
| CRM_Estados | 16 | 10 | Chave |
| CRM_GruposProcessos | 3 | 8 | — |
| CRM_Inbox | 7 | 23 | — |
| CRM_ProcessosAtividades | 70 | 4 | Chave |
| CRM_RelGruposProcessos | 0 | 6 | — |
| CRM_TipoAtividadesProcessos | 36 | 19 | Chave |
| CRM_Transicoes | 90 | 3 | Chave |
| CRM_Utilizadores | 7 | 13 | Chave |
| CRM_UtilizadoresEquipas | 0 | 8 | Chave |
| CRM_UtilizadoresInbox | 13 | 7 | Chave |

### Group: IO (7 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| IO_Inbox | 0 | 12 | ID |
| IO_InboxArquivo | 0 | 11 | ID |
| IO_InboxData | 0 | 2 | ID |
| IO_MsgData | 0 | 2 | ID |
| IO_Outbox | 0 | 7 | ID |
| IO_SentItems | 0 | 6 | ID |
| IO_Users | 0 | 5 | UserName, Contexto |

### Group: ATR (5 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ATR_Atributos | 795 | 12 | Chave |
| ATR_ContextosTiposAtributos | 30 | 11 | Chave |
| ATR_Listas | 4 | 6 | Chave |
| ATR_RelContextosAtributos | 40 | 11 | Chave |
| ATR_TiposDados | 16 | 12 | Chave |

### Group: Clientes (4 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Clientes2011 | 102 | 1 | — |
| Clientes2012 | 84 | 1 | — |
| Clientes2013 | 73 | 1 | — |
| Clientes2014 | 68 | 1 | — |

### Group: Pos (4 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Pos03 | 0 | 15 | Chave |
| Pos51 | 0 | 4 | — |
| Pos52 | 0 | 6 | — |
| Pos70 | 0 | 46 | Chave |

### Group: Doc (3 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Doc001 | 21286 | 80 | Chave |
| Doc001_Delete | 603 | 80 | — |
| Doc005 | 3 | 3 | Chave |

### Group: LinDoc (3 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| LinDoc001 | 63769 | 84 | Chave |
| LinDoc002 | 0 | 33 | Chave |
| LinDoc003 | 0 | 10 | Chave |

### Group: Chicken (2 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Chicken01 | 0 | 14 | Chave |
| Chicken02 | 0 | 18 | Chave |

### Group: LinPlan (2 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| LinPlan001 | 0 | 24 | Chave |
| LinPlan002 | 0 | 9 | Chave |

### Group: Lindoc (2 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Lindoc001_Delete | 1939 | 84 | — |
| Lindoc005 | 16 | 4 | Chave |

### Group: Plan (2 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Plan001 | 0 | 18 | Chave |
| Plan002 | 0 | 15 | Chave |

### Group: AVencimento (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AVencimento | 3 | 17 | Chave |

### Group: Acessos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Acessos | 3 | 9 | — |

### Group: Anexos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Anexos | 12 | 20 | Chave |

### Group: AnexosCat (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosCat | 0 | 3 | Chave |

### Group: AnexosGrpDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosGrpDoc | 5 | 9 | Chave |

### Group: AnexosGrpDocTp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosGrpDocTp | 15 | 4 | Chave |

### Group: AnexosIndexantes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosIndexantes | 0 | 9 | Chave |

### Group: AnexosPalavrasChave (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosPalavrasChave | 11 | 4 | Chave |

### Group: AnexosTiposDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosTiposDoc | 57 | 10 | Chave |

### Group: AnexosTiposDocIndexantes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| AnexosTiposDocIndexantes | 0 | 3 | Chave |

### Group: ArtArm (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtArm | 3026 | 29 | Chave |

### Group: ArtComp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtComp | 0 | 8 | Chave |

### Group: ArtDim (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtDim | 0 | 4 | Chave |

### Group: ArtEmp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtEmp | 1958 | 51 | Chave |

### Group: ArtEnt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtEnt | 0 | 3 | chave |

### Group: ArtLng (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtLng | 0 | 4 | Chave |

### Group: ArtMerc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtMerc | 6 | 25 | Chave |

### Group: ArtProp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtProp | 0 | 26 | Chave |

### Group: ArtPsion (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtPsion | 0 | 5 | Chave |

### Group: ArtRef (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtRef | 0 | 6 | Chave |

### Group: ArtSubst (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtSubst | 0 | 3 | Chave |

### Group: ArtUnid (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtUnid | 0 | 5 | Chave |

### Group: ArtUnidWeb (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ArtUnidWeb | 0 | 4 | Chave |

### Group: Artigos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Artigos | 2720 | 126 | Chave |

### Group: Avaliacoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Avaliacoes | 39 | 16 | Chave |

### Group: Bancos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Bancos | 25 | 15 | Chave |

### Group: CCO (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CCO | 34906 | 38 | Chave |

### Group: CCOLIQ (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CCOLIQ | 56566 | 9 | Chave |

### Group: CTB (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CTB | 23765 | 14 | — |

### Group: Carteiras (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Carteiras | 10 | 13 | Chave |

### Group: Cartoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Cartoes | 0 | 13 | Chave |

### Group: Chats (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Chats | 37 | 14 | Chave |

### Group: Classificacoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Classificacoes | 0 | 13 | Chave |

### Group: Classificadores (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Classificadores | 0 | 17 | Chave |

### Group: Comissoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Comissoes | 0 | 7 | Chave |

### Group: ComissoesPeriodos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ComissoesPeriodos | 0 | 14 | Chave |

### Group: CondPag (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| CondPag | 15 | 16 | Chave |

### Group: Consumos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Consumos | 0 | 40 | Chave |

### Group: ContCred (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ContCred | 4 | 15 | Chave |

### Group: Contactos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Contactos | 30 | 9 | Chave |

### Group: DocCart (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| DocCart | 25 | 4 | Chave |

### Group: Entidades (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Entidades | 1955 | 119 | Chave |

### Group: EntidadesRelacoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| EntidadesRelacoes | 1898 | 8 | — |

### Group: Eventos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Eventos | 0 | 7 | Chave |

### Group: Expedicoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Expedicoes | 21 | 11 | Chave |

### Group: FO (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| FO | 9630 | 69 | Chave |

### Group: FOF (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| FOF | 2 | 65 | Chave |

### Group: Fields (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Fields | 370 | 11 | Chave |

### Group: GrTam (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| GrTam | 0 | 11 | Chave |

### Group: GrpDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| GrpDoc | 21 | 12 | Chave |

### Group: GrpDocTp (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| GrpDocTp | 67 | 4 | Chave |

### Group: Hardware (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Hardware | 2 | 8 | Chave |

### Group: Horarios (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Horarios | 0 | 14 | Chave |

### Group: ImageRead (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ImageRead | 6 | 4 | — |

### Group: Impressoras (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Impressoras | 5 | 12 | Chave |

### Group: LangFields (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| LangFields | 597 | 11 | Chave |

### Group: Language (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Language | 2 | 8 | Chave |

### Group: Licencas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Licencas | 32 | 18 | Chave |

### Group: LinDOc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| LinDOc001_GrFamilia | 57820 | 2 | — |

### Group: Linguas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Linguas | 0 | 12 | Chave |

### Group: Lotes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Lotes | 1 | 15 | Chave |

### Group: Meses (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Meses | 0 | 10 | Chave |

### Group: ModoPag (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ModoPag | 1 | 13 | Chave |

### Group: ModosEntrega (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| ModosEntrega | 0 | 12 | Chave |

### Group: Moeda (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Moeda | 3 | 18 | Chave |

### Group: MultiDim (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| MultiDim | 0 | 14 | Chave |

### Group: Numeradores (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Numeradores | 47 | 12 | Chave |

### Group: Operacoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Operacoes | 0 | 27 | Chave |

### Group: PckTransactions (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PckTransactions | 0 | 5 | Id, Chave, Tabela |

### Group: Pessoal (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Pessoal | 0 | 21 | Chave |

### Group: Planos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Planos | 0 | 19 | Chave |

### Group: PortalBanners (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalBanners | 136 | 10 | Chave |

### Group: PortalContacts (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalContacts | 2 | 22 | Chave |

### Group: PortalDestak (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalDestak | 0 | 11 | Chave |

### Group: PortalDetails (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalDetails | 74 | 14 | Chave |

### Group: PortalDetailsGeral (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalDetailsGeral | 8 | 13 | Chave |

### Group: PortalFields (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalFields | 8 | 11 | Chave |

### Group: PortalLangFields (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalLangFields | 24 | 11 | Chave |

### Group: PortalLanguage (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalLanguage | 2 | 8 | Chave |

### Group: PortalMenu (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalMenu | 6 | 10 | Chave |

### Group: PortalMenuEng (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalMenuEng | 5 | 10 | Chave |

### Group: PortalNews (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalNews | 19 | 11 | Chave |

### Group: PortalPartners (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalPartners | 4 | 11 | Chave |

### Group: PortalProdDetails (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalProdDetails | 32 | 19 | Chave |

### Group: PortalProdFields (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalProdFields | 32 | 12 | Chave |

### Group: PortalSubMenu (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalSubMenu | 11 | 10 | Chave |

### Group: PortalSubMenuEng (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalSubMenuEng | 11 | 11 | Chave |

### Group: PortalSubSubjects (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalSubSubjects | 3 | 11 | Chave |

### Group: PortalTestimony (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PortalTestimony | 0 | 11 | Chave |

### Group: PosOperacoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PosOperacoes | 0 | 11 | Chave |

### Group: Postos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Postos | 13 | 47 | Chave |

### Group: Priority (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Priority | 3 | 10 | Chave |

### Group: PsionCab (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PsionCab | 0 | 7 | — |

### Group: PsionLin (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| PsionLin | 0 | 9 | — |

### Group: RegTpIVA (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| RegTpIVA | 19 | 6 | Chave |

### Group: RegimesIVA (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| RegimesIVA | 13 | 17 | Chave |

### Group: RequestTypes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| RequestTypes | 5 | 9 | Chave |

### Group: Requests (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Requests | 22 | 25 | Chave |

### Group: Rotas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Rotas | 0 | 17 | Chave |

### Group: SNCFiles (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SNCFiles | 12 | 5 | — |

### Group: SYSLOCK (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYSLOCK | 0 | 37 | — |

### Group: SYSLOG (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYSLOG | 6260 | 10 | ChaveReg |

### Group: SYSProfiles (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYSProfiles | 0 | 19 | Chave |

### Group: SYSProfilesPerm (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| SYSProfilesPerm | 0 | 4 | Chave |

### Group: Seccoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Seccoes | 0 | 12 | Chave |

### Group: Sessoes (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Sessoes | 0 | 7 | Chave |

### Group: Severity (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Severity | 3 | 10 | Chave |

### Group: Software (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Software | 16 | 8 | Chave |

### Group: Status (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Status | 6 | 8 | Chave |

### Group: TabClassif (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TabClassif | 0 | 8 | Chave |

### Group: Taras (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Taras | 0 | 10 | Chave |

### Group: Tasks (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Tasks | 13 | 20 | Chave |

### Group: Telefone (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Telefone | 105 | 5 | — |

### Group: TempX (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TempX | 94 | 9 | — |

### Group: Tempos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Tempos2 | 0 | 14 | Chave |

### Group: TiposComissao (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposComissao | 0 | 14 | Chave |

### Group: TiposContas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposContas | 6 | 13 | Chave |

### Group: TiposDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDoc | 35 | 64 | Chave |

### Group: TiposDocAT (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocAT | 24 | 9 | Chave |

### Group: TiposDocCCO (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocCCO | 37 | 45 | Chave |

### Group: TiposDocCtb (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocCtb | 9 | 22 | Chave |

### Group: TiposDocLin (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocLin | 110 | 4 | Chave |

### Group: TiposDocLinCtb (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocLinCtb | 10 | 16 | Chave |

### Group: TiposDocPst (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposDocPst | 214 | 11 | Chave |

### Group: TiposEmbalagem (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposEmbalagem | 0 | 14 | Chave |

### Group: TiposInt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposInt | 16 | 28 | Chave |

### Group: TiposIntL (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposIntL | 24 | 13 | Chave |

### Group: TiposIva (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposIva | 4 | 14 | Chave |

### Group: TiposLin (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposLin | 46 | 64 | Chave |

### Group: TiposLinSTC (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposLinSTC | 43 | 34 | Chave |

### Group: TiposSerieNum (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposSerieNum | 124 | 7 | Chave |

### Group: TiposSerieTpDoc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TiposSerieTpDoc | 0 | 4 | Chave |

### Group: TmpCCO (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpCCO | 0 | 16 | — |

### Group: TmpConf (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpConf | 0 | 17 | — |

### Group: TmpEtiq (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpEtiq | 2504 | 9 | — |

### Group: TmpInt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpInt | 8 | 77 | — |

### Group: TmpIntAn (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpIntAn | 0 | 5 | — |

### Group: TmpMultiDim (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpMultiDim | 0 | 11 | — |

### Group: TmpObras (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpObras | 0 | 13 | — |

### Group: TmpStc (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpStc | 0 | 5 | — |

### Group: TmpX (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TmpX | 0 | 9 | — |

### Group: TpContactos (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpContactos | 1 | 13 | Chave |

### Group: TpContas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpContas | 0 | 7 | — |

### Group: TpDocATSerie (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpDocATSerie | 8 | 4 | Chave |

### Group: TpDocML (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpDocML | 0 | 3 | Chave |

### Group: TpEnt (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| TpEnt | 0 | 13 | Chave |

### Group: Unidades (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Unidades | 2 | 17 | Chave |

### Group: Vendedores (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Vendedores | 11 | 24 | Chave |

### Group: Zonas (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| Zonas | 1 | 13 | Chave |

### Group: Other (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| _a | 275 | 1 | — |

### Group: image (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| image | 13 | 4 | — |

### Group: sys (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| sys99n | 8 | 58 | — |

### Group: tmporder (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| tmporder | 0 | 8 | — |

### Group: tmpsession (1 tables)

| Table | Rows | Cols | PK |
|---|---|---|---|
| tmpsession | 11 | 8 | chave |

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