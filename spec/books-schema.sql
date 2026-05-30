-- books-schema.sql
-- Canonical SQLite schema for the books.sqlite database inside a .khata archive.
--
-- STATUS: reference-implementation schema, version 12 (SCHEMA_VERSION = 12).
--
-- This is the actual DDL emitted by the reference implementation (Bahi). The abstract
-- skeleton it replaced has been retired: now that Bahi exercises the schema against real
-- workflows — invoices, purchases, ledger, stock (WAC + FIFO), GST returns, TDS/TCS,
-- the audit log, multi-year sample files — the spec tracks the real schema rather than a
-- parallel model. Other .khata implementations should follow this as the baseline and add
-- their own tables under a reserved prefix to avoid conflicts.
--
-- Conventions:
--   1. Money is stored as INTEGER paise everywhere — never floats.
--   2. Every posted document snapshots the reference data it depends on (company identity,
--      tax rate, party details, HSN description) at posting time, so later reference-data
--      edits never alter historical records.
--   3. Tax/cess rates are stored as literal values on lines, not as FKs to a mutable table.
--   4. States are 2-letter ISO 3166-2:IN codes throughout.
--   5. The append-only audit log lives in the `audit_log` table below; the manifest mirrors
--      the chain head (integrity.auditHead) and signing key (integrity.signedBy). The hash
--      chain and its versioning are defined in spec/audit-log.md.
--   6. Compensation cess: header `cess` columns on invoices/purchases and per-line `cess`
--      columns; rate derivation per spec/cess-schema.md.
--
-- Schema-version history (migrations applied in order on file open):
--   v9  Phase 8A — payments.vendor_id / payment_direction / tds_amount / tds_section
--   v10 audit_log.hash_version (versioned tamper-evident audit hash; see audit-log.md)
--   v11 invoice_lines.cess (per-line compensation cess on sales)
--   v12 purchase_lines.cess (per-line compensation cess on purchases / ITC)
--
-- Last revised 2026-05-30: replaced the abstract skeleton with the reference
-- implementation's schema 12 DDL. See spec/CHANGELOG.md.
--
-- Notes on PRAGMAs: the reference implementation runs SQLite via sql.js (WASM, in-memory);
-- foreign-key enforcement is implementation-dependent (off by default in sql.js). Treat the
-- REFERENCES clauses below as the intended relationships regardless of runtime enforcement.

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  parent_id INTEGER,
  type TEXT NOT NULL CHECK(type IN ('asset','liability','equity','income','expense')),
  system_flag INTEGER DEFAULT 0,
  archived INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_accounts_name ON accounts(name);
CREATE INDEX IF NOT EXISTS idx_accounts_parent ON accounts(parent_id);

CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  posted_at TEXT NOT NULL,
  voucher_type TEXT NOT NULL,
  voucher_ref TEXT,
  narration TEXT,
  created_by TEXT,
  created_at TEXT NOT NULL,
  reversed_by_id INTEGER,
  is_amendment INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_entries_posted ON entries(posted_at);
CREATE INDEX IF NOT EXISTS idx_entries_voucher ON entries(voucher_type);

CREATE TABLE IF NOT EXISTS entry_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id INTEGER NOT NULL REFERENCES entries(id),
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  debit INTEGER NOT NULL DEFAULT 0,
  credit INTEGER NOT NULL DEFAULT 0,
  -- Frozen snapshot of accounts.name at posting time (Invariant 7).
  -- Reports and ledger views must read from this column for historical periods,
  -- not from a live JOIN against accounts.name. The live name is for the master
  -- list only. Renaming an account never silently relabels old postings.
  account_name TEXT
);
CREATE INDEX IF NOT EXISTS idx_lines_entry ON entry_lines(entry_id);
CREATE INDEX IF NOT EXISTS idx_lines_account ON entry_lines(account_id);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  ref TEXT,
  origin TEXT,           -- window.location.origin (or 'file://') at time of write. Forensic field.
  payload TEXT,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL,
  signature TEXT,
  hash_version INTEGER   -- H1: 2 = all-field hash; NULL/absent = legacy v1 (origin+payload only)
);

CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY,
  v TEXT
);

-- === Phase 2A — Freelancer tier ===

CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  gstin TEXT,
  pan TEXT,
  state TEXT,                       -- ISO 3166-2:IN code
  email TEXT,
  phone TEXT,
  address TEXT,
  opening_balance INTEGER DEFAULT 0,  -- paise; +ve = customer owes us
  archived INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);
CREATE INDEX IF NOT EXISTS idx_customers_gstin ON customers(gstin);

CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  hsn_sac TEXT,
  is_service INTEGER DEFAULT 0,
  unit TEXT,
  default_rate INTEGER,            -- paise per unit
  default_tax_rate REAL,           -- 0.00 to 0.28
  archived INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);

CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_number TEXT NOT NULL UNIQUE,
  series TEXT NOT NULL DEFAULT 'default',
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  invoice_date TEXT NOT NULL,
  due_date TEXT,
  place_of_supply TEXT,            -- ISO state code
  place_of_supply_name TEXT,       -- Frozen state name at posting time (Invariant 4)
  is_export INTEGER DEFAULT 0,
  is_sez INTEGER DEFAULT 0,
  reverse_charge INTEGER DEFAULT 0,
  subtotal INTEGER NOT NULL DEFAULT 0,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  cess INTEGER NOT NULL DEFAULT 0,
  round_off INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'posted', -- 'draft' | 'posted' | 'cancelled'
  ledger_entry_id INTEGER REFERENCES entries(id),
  -- Frozen JSON snapshots at posting time (Invariants 1 and 6).
  -- Reprints, GSTR-1 export, and any historical view MUST read from these,
  -- not from STATE.manifest.company or a live JOIN on customers.
  company_snapshot TEXT,           -- JSON: {name, gstin, pan, state, stateName, gstinStateCode, ...}
  customer_snapshot TEXT,          -- JSON: {name, gstin, pan, state, stateName, address, email, phone}
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id);

CREATE TABLE IF NOT EXISTS invoice_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  line_no INTEGER NOT NULL,
  item_id INTEGER REFERENCES items(id),
  description TEXT NOT NULL,
  hsn_sac TEXT,
  -- Frozen HSN/SAC description at posting time (Invariant 3). Reprint MUST read this,
  -- not look up the description from current REF.hsnCommon / REF.sacCommon.
  hsn_description TEXT,
  quantity REAL NOT NULL DEFAULT 1,
  unit TEXT,
  rate INTEGER NOT NULL,           -- paise per unit
  discount INTEGER DEFAULT 0,      -- paise (line-level absolute)
  taxable INTEGER NOT NULL,        -- (qty*rate - discount)
  -- tax_rate is the literal frozen rate at posting time (Invariant 2). The rate value
  -- is the source of truth for this line FOREVER. Never recompute from a current rate
  -- table. rate_id is the forensic key (e.g., "gst-18") for traceability — captured by
  -- rateIdForDecimal() at posting time, may be null on legacy v2 rows.
  tax_rate REAL NOT NULL,          -- 0.00 to 0.28
  rate_id TEXT,                    -- Forensic key into REF.gstRates (v3+)
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  cess INTEGER NOT NULL DEFAULT 0,  -- H8: GST compensation cess (paise)
  total INTEGER NOT NULL           -- taxable + tax components + cess
);
CREATE INDEX IF NOT EXISTS idx_invoice_lines_invoice ON invoice_lines(invoice_id);

-- === Phase 2B.2 — Payments / receipts ===
-- Closes the invoice → cash loop. A payment is a header row with N allocation lines,
-- one per invoice it clears. Posting to the ledger is Dr {bank/cash account} / Cr Sundry
-- Debtors. Per-customer outstanding is computed from invoices.total - SUM(allocations).

CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payment_number TEXT NOT NULL UNIQUE,
  payment_date TEXT NOT NULL,
  customer_id INTEGER REFERENCES customers(id),
  bank_account_id INTEGER NOT NULL REFERENCES accounts(id),
  amount INTEGER NOT NULL DEFAULT 0,    -- paise; total of all allocations
  payment_mode TEXT,                    -- 'cash' | 'cheque' | 'neft' | 'rtgs' | 'imps' | 'upi' | 'card' | 'other'
  reference TEXT,                       -- cheque number / UTR / transaction id
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'posted',
  ledger_entry_id INTEGER REFERENCES entries(id),
  -- Frozen snapshots at posting time (Invariants 1, 6 — historical integrity)
  customer_snapshot TEXT,               -- JSON same shape as invoices.customer_snapshot
  bank_account_snapshot TEXT,           -- account name as a literal string
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payments_customer ON payments(customer_id);
CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date);

CREATE TABLE IF NOT EXISTS payment_allocations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payment_id INTEGER NOT NULL REFERENCES payments(id),
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  amount INTEGER NOT NULL DEFAULT 0,    -- paise allocated to this invoice
  invoice_number_snapshot TEXT          -- frozen so allocation history reads cleanly
);
CREATE INDEX IF NOT EXISTS idx_alloc_payment ON payment_allocations(payment_id);
CREATE INDEX IF NOT EXISTS idx_alloc_invoice ON payment_allocations(invoice_id);

-- === Phase 2B.6 — Advance receipts ===
-- Under GST, an advance received before the invoice triggers a tax liability.
-- An advance is recorded as: Dr Bank/Cash (gross) / Cr Customer Advances Received
-- (taxable principal) / Cr {CGST|SGST|IGST} Output @ {rate}% (tax). When an invoice
-- is later raised against the same customer, the user can apply the advance — that
-- creates a row in advance_adjustments and posts a reversing entry that flows the
-- liability + GST off the advances account into the customer's outstanding balance.

CREATE TABLE IF NOT EXISTS advances (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  advance_number TEXT NOT NULL UNIQUE,
  advance_date TEXT NOT NULL,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  bank_account_id INTEGER NOT NULL REFERENCES accounts(id),
  amount INTEGER NOT NULL,                  -- gross paise (taxable + tax)
  taxable INTEGER NOT NULL,                 -- principal portion
  tax_rate REAL NOT NULL,
  rate_id TEXT,                             -- forensic key into REF.gstRates
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  place_of_supply TEXT,                     -- ISO state
  place_of_supply_name TEXT,                -- frozen state name
  nature_of_supply TEXT,                    -- 'goods' | 'services'
  payment_mode TEXT,
  reference TEXT,
  notes TEXT,
  adjusted_amount INTEGER NOT NULL DEFAULT 0, -- running total of all adjustments
  remaining_balance INTEGER NOT NULL,       -- amount - adjusted_amount
  status TEXT NOT NULL DEFAULT 'open',      -- 'open' | 'fully-adjusted' | 'refunded'
  ledger_entry_id INTEGER REFERENCES entries(id),
  customer_snapshot TEXT,                   -- frozen JSON
  bank_account_snapshot TEXT,               -- frozen account name
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_advances_customer ON advances(customer_id);
CREATE INDEX IF NOT EXISTS idx_advances_date ON advances(advance_date);
CREATE INDEX IF NOT EXISTS idx_advances_status ON advances(status);

CREATE TABLE IF NOT EXISTS advance_adjustments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  advance_id INTEGER NOT NULL REFERENCES advances(id),
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  amount INTEGER NOT NULL,                  -- gross adjusted amount
  ledger_entry_id INTEGER REFERENCES entries(id),
  advance_number_snapshot TEXT,
  invoice_number_snapshot TEXT,
  adjusted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_advadj_advance ON advance_adjustments(advance_id);
CREATE INDEX IF NOT EXISTS idx_advadj_invoice ON advance_adjustments(invoice_id);

-- === Phase 2B.7 — Invoice series ===
-- Multiple concurrent invoice series per company (domestic, export, SEZ-WP, SEZ-WOP,
-- bill of supply, etc). Each series has its own counter that's used by nextInvoiceNumber.
-- The series name is stored on each invoice in the existing invoices.series column.
-- Defaults are seeded on file create; users can add/edit via the series master view.

CREATE TABLE IF NOT EXISTS invoice_series (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,                -- 'Domestic' | 'Export' | etc — also the FK in invoices.series
  prefix TEXT NOT NULL,                     -- 'INV' | 'EXP' | 'SEZ-WP' | etc
  suffix TEXT,                              -- optional, e.g. '/25-26'
  starting_number INTEGER NOT NULL DEFAULT 1,
  reset_on_fy INTEGER DEFAULT 1,
  default_for TEXT,                         -- 'domestic' | 'export' | 'sez-wp' | 'sez-wop' | 'bos' | 'credit-note' | NULL
  archived INTEGER DEFAULT 0,
  system_flag INTEGER DEFAULT 0,            -- 1 = seeded default, 0 = user-created
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invoice_series_default ON invoice_series(default_for);

-- === Phase 3 — Service SMB tier ===

-- Vendors are the mirror of customers — same fields plus a few purchase-specific ones.
CREATE TABLE IF NOT EXISTS vendors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  gstin TEXT,
  pan TEXT,
  state TEXT,                       -- ISO 3166-2:IN
  email TEXT,
  phone TEXT,
  address TEXT,
  rcm_applicable INTEGER DEFAULT 0, -- 1 = supplies are notified RCM categories
  tds_section TEXT,                 -- Default TDS section to apply (e.g. '194C', '194J')
  opening_balance INTEGER DEFAULT 0,-- paise; +ve = we owe vendor
  archived INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vendors_name ON vendors(name);
CREATE INDEX IF NOT EXISTS idx_vendors_gstin ON vendors(gstin);

-- Purchases are the mirror of invoices with reversed posting:
--   Dr Purchases (taxable) + Dr GST Input (per rate) + Cr Sundry Creditors (total)
-- For RCM purchases:
--   Dr Purchases (taxable) + Dr GST RCM Input + Cr GST RCM Output + Cr Sundry Creditors (taxable)
CREATE TABLE IF NOT EXISTS purchases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bill_number TEXT NOT NULL,        -- vendor's bill number, NOT auto-generated
  internal_ref TEXT NOT NULL UNIQUE,-- Bahi's internal reference (PUR/{FY}/{NNNN})
  vendor_id INTEGER NOT NULL REFERENCES vendors(id),
  bill_date TEXT NOT NULL,
  due_date TEXT,
  place_of_supply TEXT,             -- ISO state code
  place_of_supply_name TEXT,        -- frozen
  is_import INTEGER DEFAULT 0,
  reverse_charge INTEGER DEFAULT 0, -- 1 = RCM
  itc_eligible INTEGER DEFAULT 1,   -- 0 = blocked credits (motor vehicles, etc.)
  subtotal INTEGER NOT NULL DEFAULT 0,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  cess INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'posted',
  ledger_entry_id INTEGER REFERENCES entries(id),
  -- FROZEN snapshots at posting time (Invariants 1, 6)
  company_snapshot TEXT,
  vendor_snapshot TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_purchases_date ON purchases(bill_date);
CREATE INDEX IF NOT EXISTS idx_purchases_vendor ON purchases(vendor_id);

CREATE TABLE IF NOT EXISTS purchase_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_id INTEGER NOT NULL REFERENCES purchases(id),
  line_no INTEGER NOT NULL,
  item_id INTEGER REFERENCES items(id),
  description TEXT NOT NULL,
  hsn_sac TEXT,
  hsn_description TEXT,             -- FROZEN
  quantity REAL NOT NULL DEFAULT 1,
  unit TEXT,
  rate INTEGER NOT NULL,            -- paise per unit
  discount INTEGER DEFAULT 0,
  taxable INTEGER NOT NULL,
  tax_rate REAL NOT NULL,
  rate_id TEXT,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  itc_eligible INTEGER DEFAULT 1,
  cess INTEGER NOT NULL DEFAULT 0,  -- H8: GST compensation cess (paise)
  total INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_purchase_lines_purchase ON purchase_lines(purchase_id);

-- Credit notes are downward adjustments against existing invoices.
-- They INHERIT the original invoice's snapshot (Invariant 5 — reversals don't re-lookup).
CREATE TABLE IF NOT EXISTS credit_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cn_number TEXT NOT NULL UNIQUE,
  cn_date TEXT NOT NULL,
  original_invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  original_invoice_number TEXT NOT NULL, -- FROZEN
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  reason TEXT,                      -- 'sales-return' | 'rate-difference' | 'discount' | 'deficiency' | 'other'
  place_of_supply TEXT,
  place_of_supply_name TEXT,
  subtotal INTEGER NOT NULL DEFAULT 0,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'posted',
  ledger_entry_id INTEGER REFERENCES entries(id),
  -- Inherited snapshots from the original invoice
  company_snapshot TEXT,
  customer_snapshot TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cn_date ON credit_notes(cn_date);
CREATE INDEX IF NOT EXISTS idx_cn_invoice ON credit_notes(original_invoice_id);

CREATE TABLE IF NOT EXISTS credit_note_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cn_id INTEGER NOT NULL REFERENCES credit_notes(id),
  line_no INTEGER NOT NULL,
  description TEXT NOT NULL,
  hsn_sac TEXT,
  hsn_description TEXT,             -- inherited
  quantity REAL NOT NULL DEFAULT 1,
  rate INTEGER NOT NULL,
  taxable INTEGER NOT NULL,
  tax_rate REAL NOT NULL,           -- inherited from original invoice line
  rate_id TEXT,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL
);

-- Debit notes are upward adjustments against existing purchases.
CREATE TABLE IF NOT EXISTS debit_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dn_number TEXT NOT NULL UNIQUE,
  dn_date TEXT NOT NULL,
  original_purchase_id INTEGER NOT NULL REFERENCES purchases(id),
  original_bill_number TEXT NOT NULL,
  vendor_id INTEGER NOT NULL REFERENCES vendors(id),
  reason TEXT,
  place_of_supply TEXT,
  place_of_supply_name TEXT,
  subtotal INTEGER NOT NULL DEFAULT 0,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'posted',
  ledger_entry_id INTEGER REFERENCES entries(id),
  company_snapshot TEXT,
  vendor_snapshot TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dn_date ON debit_notes(dn_date);
CREATE INDEX IF NOT EXISTS idx_dn_purchase ON debit_notes(original_purchase_id);

CREATE TABLE IF NOT EXISTS debit_note_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dn_id INTEGER NOT NULL REFERENCES debit_notes(id),
  line_no INTEGER NOT NULL,
  description TEXT NOT NULL,
  hsn_sac TEXT,
  hsn_description TEXT,
  quantity REAL NOT NULL DEFAULT 1,
  rate INTEGER NOT NULL,
  taxable INTEGER NOT NULL,
  tax_rate REAL NOT NULL,
  rate_id TEXT,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL
);

-- TDS deductions are recorded per payment-out (vendor payment) when applicable.
CREATE TABLE IF NOT EXISTS tds_deductions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payment_id INTEGER REFERENCES payments(id), -- parent payment row (vendor payments use payments table too)
  vendor_id INTEGER REFERENCES vendors(id),
  section TEXT NOT NULL,            -- '194C', '194J', etc.
  rate REAL NOT NULL,               -- 0.10 = 10%
  taxable_amount INTEGER NOT NULL,  -- the amount on which TDS was computed
  tds_amount INTEGER NOT NULL,      -- the actual TDS withheld
  payment_date TEXT NOT NULL,
  vendor_pan TEXT,                  -- frozen
  vendor_name_snapshot TEXT,        -- frozen
  ledger_entry_id INTEGER REFERENCES entries(id),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tds_vendor ON tds_deductions(vendor_id);
CREATE INDEX IF NOT EXISTS idx_tds_section ON tds_deductions(section);

-- TCS collections are recorded per invoice line where Section 206C(1H) threshold has been crossed.
CREATE TABLE IF NOT EXISTS tcs_collections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER REFERENCES invoices(id),
  customer_id INTEGER REFERENCES customers(id),
  section TEXT NOT NULL,            -- '206C(1H)' typically
  rate REAL NOT NULL,               -- 0.001 = 0.1%
  taxable_amount INTEGER NOT NULL,
  tcs_amount INTEGER NOT NULL,
  invoice_date TEXT NOT NULL,
  customer_pan TEXT,
  customer_name_snapshot TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tcs_customer ON tcs_collections(customer_id);

-- Period locks. Once a return is marked filed for a period, edits to entries dated in that
-- period are flagged as amendments (is_amendment column already exists on entries).
CREATE TABLE IF NOT EXISTS period_locks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  return_type TEXT NOT NULL,        -- 'gstr1' | 'gstr3b' | 'cmp08' | 'gstr4' | '26q' | '27eq'
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  filed_at TEXT NOT NULL,
  filed_by TEXT,
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_period_locks_type ON period_locks(return_type);

-- FY closings track which financial years have been closed via the rollover wizard.
CREATE TABLE IF NOT EXISTS fy_closings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fy_start TEXT NOT NULL,           -- e.g. '2024-04-01'
  fy_end TEXT NOT NULL,             -- e.g. '2025-03-31'
  closed_at TEXT NOT NULL,
  closing_entry_id INTEGER REFERENCES entries(id),
  net_profit INTEGER NOT NULL DEFAULT 0,  -- paise
  carried_forward INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fy_closings ON fy_closings(fy_start);

-- === Phase 4 — Goods SMB tier ===

-- Godowns (warehouses, stock locations).
-- Single 'Main' godown auto-seeded on v6→v7 migration. Multi-godown UI is unlocked
-- from Settings → Inventory once the user creates a second godown.
CREATE TABLE IF NOT EXISTS godowns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  address TEXT,
  state TEXT,                       -- ISO 3166-2:IN (for inter-GSTIN transfers)
  is_default INTEGER DEFAULT 0,
  archived INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);

-- Batches: every "lot" of an item that came in via a purchase or opening stock.
-- For FIFO items: every batch is one row, dequeued oldest-first on outward.
-- For batch-tracked items: user-named batch with mfg/expiry, picker on every line.
-- For WAC items: a single synthetic "WAC" batch row per (item, godown), updated in place.
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id),
  godown_id INTEGER NOT NULL REFERENCES godowns(id),
  batch_no TEXT,                    -- NULL for WAC synthetic; auto-gen for FIFO; user-typed for batch-tracked
  mfg_date TEXT,
  expiry_date TEXT,
  source_purchase_id INTEGER REFERENCES purchases(id),
  source_purchase_line_id INTEGER REFERENCES purchase_lines(id),
  qty_in INTEGER NOT NULL DEFAULT 0,    -- in item base unit (paise-style integer for sub-unit precision)
  qty_out INTEGER NOT NULL DEFAULT 0,
  qty_balance INTEGER NOT NULL DEFAULT 0,
  rate INTEGER NOT NULL,            -- paise per unit at the time of inward
  value_in INTEGER NOT NULL DEFAULT 0,  -- paise — qty_in × rate
  value_out INTEGER NOT NULL DEFAULT 0,
  value_balance INTEGER NOT NULL DEFAULT 0,
  is_wac_synthetic INTEGER DEFAULT 0,   -- 1 = the WAC running-average row, never closed
  status TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'exhausted' | 'expired'
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_batches_item ON batches(item_id);
CREATE INDEX IF NOT EXISTS idx_batches_godown ON batches(godown_id);
CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status);

-- Stock movements: the append-only log. Every stock change writes one row here, plus
-- the batch row(s) it touched. Reports read from here for movement history.
CREATE TABLE IF NOT EXISTS stock_movements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id),
  godown_id INTEGER NOT NULL REFERENCES godowns(id),
  batch_id INTEGER REFERENCES batches(id),
  movement_type TEXT NOT NULL,      -- 'in' | 'out' | 'transfer' | 'adjust'
  voucher_type TEXT NOT NULL,       -- 'purchase' | 'invoice' | 'delivery-challan' | 'opening' | 'transfer' | 'adjustment' | 'credit-note' | 'debit-note'
  voucher_id INTEGER,
  voucher_ref TEXT,
  posted_at TEXT NOT NULL,
  qty INTEGER NOT NULL,             -- positive = in, negative = out
  rate INTEGER NOT NULL,            -- paise per unit, frozen
  value INTEGER NOT NULL,           -- paise, signed
  -- FROZEN snapshots
  item_name_snapshot TEXT,
  unit_snapshot TEXT,
  godown_name_snapshot TEXT,
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stock_mov_item ON stock_movements(item_id);
CREATE INDEX IF NOT EXISTS idx_stock_mov_date ON stock_movements(posted_at);
CREATE INDEX IF NOT EXISTS idx_stock_mov_voucher ON stock_movements(voucher_type, voucher_id);

-- Delivery challans: stock leaves (or returns) without a sale.
CREATE TABLE IF NOT EXISTS delivery_challans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  challan_number TEXT NOT NULL UNIQUE,
  challan_date TEXT NOT NULL,
  challan_type TEXT NOT NULL,       -- 'outward-job' | 'outward-sample' | 'outward-return' | 'inward-return'
  customer_id INTEGER REFERENCES customers(id),
  vendor_id INTEGER REFERENCES vendors(id),
  godown_id INTEGER NOT NULL REFERENCES godowns(id),
  destination TEXT,
  vehicle_no TEXT,
  transporter TEXT,
  reason TEXT,
  is_returnable INTEGER DEFAULT 0,
  expected_return_date TEXT,
  linked_invoice_id INTEGER REFERENCES invoices(id),
  status TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'received-back' | 'invoiced' | 'cancelled'
  -- FROZEN snapshots
  company_snapshot TEXT,
  party_snapshot TEXT,
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dc_date ON delivery_challans(challan_date);

CREATE TABLE IF NOT EXISTS delivery_challan_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  challan_id INTEGER NOT NULL REFERENCES delivery_challans(id),
  line_no INTEGER NOT NULL,
  item_id INTEGER NOT NULL REFERENCES items(id),
  description TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit TEXT,
  batch_id INTEGER REFERENCES batches(id),
  rate INTEGER,                     -- paise — informational only, no GL posting
  notes TEXT
);

-- E-way bills: generated from an invoice or delivery challan or stock transfer.
CREATE TABLE IF NOT EXISTS eway_bills (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ewb_number TEXT,                  -- from the NIC portal, filled in later
  ewb_date TEXT NOT NULL,
  source_type TEXT NOT NULL,        -- 'invoice' | 'delivery-challan' | 'stock-transfer'
  source_id INTEGER NOT NULL,
  source_ref TEXT NOT NULL,
  -- Transport details
  transporter_name TEXT,
  transporter_id TEXT,
  vehicle_no TEXT,
  vehicle_type TEXT,                -- 'regular' | 'over-dimensional'
  mode TEXT,                        -- 'road' | 'rail' | 'air' | 'ship'
  distance_km INTEGER,
  reason_code TEXT,                 -- '1'=supply, '2'=export, '3'=job-work, '4'=sktd, '5'=for-own-use, '8'=others
  -- FROZEN snapshots
  supplier_snapshot TEXT,
  recipient_snapshot TEXT,
  goods_snapshot TEXT,              -- JSON array
  taxable_value INTEGER NOT NULL,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  cess INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',  -- 'draft' | 'generated' | 'cancelled'
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ewb_date ON eway_bills(ewb_date);
CREATE INDEX IF NOT EXISTS idx_ewb_number ON eway_bills(ewb_number);

-- Inter-GSTIN stock transfers (same legal entity, different GSTINs).
CREATE TABLE IF NOT EXISTS stock_transfers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  transfer_number TEXT NOT NULL UNIQUE,
  transfer_date TEXT NOT NULL,
  direction TEXT NOT NULL,          -- 'out' | 'in'
  from_gstin TEXT NOT NULL,
  from_state TEXT NOT NULL,
  to_gstin TEXT NOT NULL,
  to_state TEXT NOT NULL,
  from_godown_id INTEGER REFERENCES godowns(id),
  to_godown_id INTEGER REFERENCES godowns(id),
  linked_invoice_id INTEGER REFERENCES invoices(id),
  linked_purchase_id INTEGER REFERENCES purchases(id),
  ewb_id INTEGER REFERENCES eway_bills(id),
  total_value INTEGER NOT NULL,
  payload_snapshot TEXT,            -- JSON of the full transfer for re-export / forensics
  status TEXT NOT NULL DEFAULT 'draft',  -- 'draft' | 'sent' | 'received'
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_st_date ON stock_transfers(transfer_date);

-- === Phase 6 — CA mode ===

-- Annotations are notes attached to ledger entries (entries / invoices / purchases /
-- payments / etc.). They live inside the .khata file so they survive handoff back
-- to the owner. Each annotation captures the CA's identity at creation time —
-- snapshot pattern, never re-resolved from a live profile lookup.
CREATE TABLE IF NOT EXISTS annotations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_type TEXT NOT NULL,        -- 'entry' | 'invoice' | 'purchase' | 'payment' | 'credit-note' | 'debit-note'
  target_id INTEGER NOT NULL,
  target_ref TEXT,                  -- frozen voucher ref / invoice number for resilience
  note_type TEXT NOT NULL,          -- 'comment' | 'todo' | 'flag' | 'reclassified' | 'missing-bill' | 'confirm-with-client'
  body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'resolved' | 'wontfix'
  -- CA identity snapshot at creation time
  ca_name TEXT,
  ca_firm TEXT,
  ca_membership TEXT,
  -- Audit fields
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,         -- 'ca' or 'owner' — drives display chrome
  resolved_at TEXT,
  resolved_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_annotations_target ON annotations(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_annotations_status ON annotations(status);
CREATE INDEX IF NOT EXISTS idx_annotations_created_at ON annotations(created_at);

-- Review markers track the "last reviewed" head per entry. CA marks entries as
-- reviewed; the next review session shows everything new since the marker.
CREATE TABLE IF NOT EXISTS review_markers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id INTEGER NOT NULL REFERENCES entries(id),
  reviewed_at TEXT NOT NULL,
  reviewed_by TEXT NOT NULL,
  ca_membership TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_markers_entry ON review_markers(entry_id);

-- === Phase 8A — CA-handoff feature complete ===

-- Bank reconciliations: a manual statement-vs-book reconciliation snapshot.
-- Each row represents one reconciliation event for one bank account at one
-- closing date. matched_entry_lines is a JSON array of entry_line IDs the
-- user marked as cleared during the reconciliation session.
CREATE TABLE IF NOT EXISTS bank_reconciliations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bank_account_id INTEGER NOT NULL REFERENCES accounts(id),
  reconciled_through_date TEXT NOT NULL,
  closing_balance_per_book INTEGER NOT NULL,    -- paise
  closing_balance_per_statement INTEGER NOT NULL,
  uncleared_debits INTEGER DEFAULT 0,
  uncleared_credits INTEGER DEFAULT 0,
  difference INTEGER DEFAULT 0,
  matched_entry_lines TEXT,                      -- JSON array of entry_line IDs
  notes TEXT,
  reconciled_at TEXT NOT NULL,
  reconciled_by TEXT NOT NULL                    -- 'owner' or 'ca'
);
CREATE INDEX IF NOT EXISTS idx_bankrec_account ON bank_reconciliations(bank_account_id);
