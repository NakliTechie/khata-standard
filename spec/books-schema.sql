-- books-schema.sql
-- SQLite schema for the books.sqlite database inside a .khata archive.
--
-- STATUS: PLACEHOLDER / SKELETON
--
-- This file is a structural draft capturing the core tables every .khata
-- implementation needs. The final DDL will be locked once the Bahi reference
-- implementation completes Phase 1 and exercises the schema against real
-- workflows. Until then, expect column additions, index tuning, and
-- constraint refinements in the minor version range. No breaking changes
-- are planned between now and 1.0.
--
-- Implementations should follow this schema as a baseline and add
-- implementation-specific tables (audit, cache, etc.) under a reserved
-- prefix to avoid conflicts.
--
-- Design principles (see Bahi spec §3 and BAHI-AGENT-MSG-HISTORICAL-INTEGRITY):
--
--   1. Every posted transaction captures an immutable snapshot of relevant
--      reference data (company identity, tax rate, customer/vendor details,
--      HSN description) at posting time. Reference data is allowed to change
--      but never affects historical records.
--
--   2. Rates are stored as literal numeric values on transaction lines, not
--      as foreign keys to a mutable rate table.
--
--   3. States are stored as 2-letter ISO 3166-2:IN codes throughout.
--
--   4. Soft delete only for posted entries; drafts can be hard-deleted.
--
--   5. Audit log primary storage is in manifest.json, not here; this DB
--      carries the ledger only.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ============================================================================
-- CHART OF ACCOUNTS
-- ============================================================================

CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY,         -- stable identifier, never renamed
    parent_id TEXT REFERENCES accounts(account_id),
    name TEXT NOT NULL,                  -- display name, editable
    nature TEXT NOT NULL CHECK (nature IN ('asset', 'liability', 'income', 'expense', 'system')),
    account_type TEXT,                   -- e.g., 'current_asset', 'fixed_asset', etc.
    is_essential INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,
    opening_balance NUMERIC DEFAULT 0,
    created_at TEXT NOT NULL,
    notes TEXT
);

CREATE INDEX idx_accounts_parent ON accounts(parent_id);
CREATE INDEX idx_accounts_nature ON accounts(nature);

-- ============================================================================
-- MASTERS
-- ============================================================================

CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    gstin TEXT,
    pan TEXT,
    state_code TEXT,                     -- 2-letter ISO code
    billing_address TEXT,
    shipping_address TEXT,
    email TEXT,
    phone TEXT,
    credit_limit NUMERIC,
    opening_balance NUMERIC DEFAULT 0,
    tcs_threshold_crossed INTEGER DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE vendors (
    vendor_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    gstin TEXT,
    pan TEXT,
    state_code TEXT,
    address TEXT,
    email TEXT,
    phone TEXT,
    rcm_applicable INTEGER DEFAULT 0,
    opening_balance NUMERIC DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE items (
    item_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('goods', 'service')),
    hsn_or_sac TEXT,
    unit TEXT,                           -- 'pcs', 'kg', 'hrs', etc.
    default_sale_rate NUMERIC,
    default_purchase_rate NUMERIC,
    default_tax_rate NUMERIC,            -- percentage, e.g., 18.00
    opening_stock NUMERIC DEFAULT 0,
    reorder_level NUMERIC,
    preferred_vendor_id TEXT REFERENCES vendors(vendor_id),
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- ============================================================================
-- TRANSACTIONS (documents)
-- ============================================================================

CREATE TABLE transactions (
    transaction_id TEXT PRIMARY KEY,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN (
        'sales_invoice', 'purchase_bill', 'receipt', 'payment',
        'credit_note', 'debit_note', 'journal_voucher', 'contra',
        'delivery_challan', 'advance_receipt', 'refund_voucher'
    )),
    document_number TEXT NOT NULL,       -- e.g., 'INV-2026-0001'
    series_id TEXT,                      -- which invoice series this belongs to
    transaction_date TEXT NOT NULL,      -- ISO date
    posted_at TEXT NOT NULL,             -- ISO timestamp
    party_id TEXT,                       -- customer or vendor
    party_type TEXT CHECK (party_type IN ('customer', 'vendor', 'other')),

    -- IMMUTABLE IDENTITY SNAPSHOT at posting time
    -- These columns capture the state of reference data at posting time
    -- and NEVER change after the transaction is posted. Reprints use these.
    company_snapshot_json TEXT NOT NULL, -- company identity snapshot
    party_snapshot_json TEXT,            -- customer or vendor snapshot

    -- Totals
    subtotal NUMERIC NOT NULL,
    tax_total NUMERIC NOT NULL,
    cess_total NUMERIC DEFAULT 0,
    tcs_total NUMERIC DEFAULT 0,
    round_off NUMERIC DEFAULT 0,
    grand_total NUMERIC NOT NULL,

    -- Metadata
    place_of_supply_state_code TEXT,
    reverse_charge INTEGER DEFAULT 0,
    is_amendment INTEGER DEFAULT 0,      -- amendment to a filed-period entry
    is_reversed INTEGER DEFAULT 0,       -- has been reversed by another txn
    reversed_by TEXT REFERENCES transactions(transaction_id),
    reverses TEXT REFERENCES transactions(transaction_id),
    composition_scheme INTEGER DEFAULT 0, -- was composition scheme active at posting

    notes TEXT,
    created_by_actor TEXT,               -- 'owner' or 'ca'
    created_by_actor_name TEXT,
    created_from_origin TEXT             -- origin URL at posting time
);

CREATE INDEX idx_transactions_date ON transactions(transaction_date);
CREATE INDEX idx_transactions_type ON transactions(transaction_type);
CREATE INDEX idx_transactions_party ON transactions(party_id);
CREATE INDEX idx_transactions_document ON transactions(document_number);

CREATE TABLE transaction_lines (
    line_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id) ON DELETE CASCADE,
    line_number INTEGER NOT NULL,

    item_id TEXT REFERENCES items(item_id),

    -- IMMUTABLE snapshot of line description at posting time
    description TEXT NOT NULL,
    hsn_or_sac TEXT,
    hsn_description_snapshot TEXT,       -- HSN description as it was at posting time

    quantity NUMERIC,
    unit TEXT,
    rate NUMERIC NOT NULL,               -- per-unit rate
    discount_pct NUMERIC DEFAULT 0,
    discount_amount NUMERIC DEFAULT 0,
    taxable_value NUMERIC NOT NULL,

    -- IMMUTABLE tax snapshot — the literal rate values at posting time
    tax_rate NUMERIC NOT NULL,           -- e.g., 18.00 (store the number, not a FK)
    tax_rate_id TEXT,                    -- forensic reference, e.g., 'gst-18-standard'
    cgst_rate NUMERIC DEFAULT 0,
    cgst_amount NUMERIC DEFAULT 0,
    sgst_rate NUMERIC DEFAULT 0,
    sgst_amount NUMERIC DEFAULT 0,
    igst_rate NUMERIC DEFAULT 0,
    igst_amount NUMERIC DEFAULT 0,
    cess_rate NUMERIC DEFAULT 0,
    cess_amount NUMERIC DEFAULT 0,

    tcs_section TEXT,                    -- e.g., '206C(1H)'
    tcs_rate NUMERIC DEFAULT 0,
    tcs_amount NUMERIC DEFAULT 0,

    line_total NUMERIC NOT NULL,
    rcm_applicable INTEGER DEFAULT 0,
    itc_eligible INTEGER DEFAULT 1
);

CREATE INDEX idx_lines_transaction ON transaction_lines(transaction_id);

-- ============================================================================
-- LEDGER POSTINGS (double-entry)
-- ============================================================================
-- Every transaction produces one or more ledger postings. Debits and credits
-- must balance per transaction. This table is the authoritative ledger.

CREATE TABLE ledger_postings (
    posting_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    account_name_snapshot TEXT NOT NULL, -- name at posting time, for historical reports
    posting_date TEXT NOT NULL,          -- usually same as transaction date
    debit NUMERIC DEFAULT 0,
    credit NUMERIC DEFAULT 0,
    party_id TEXT,                       -- for sub-ledger aggregation
    narration TEXT,
    CHECK (debit >= 0 AND credit >= 0),
    CHECK (NOT (debit > 0 AND credit > 0)) -- posting is either debit or credit, not both
);

CREATE INDEX idx_postings_transaction ON ledger_postings(transaction_id);
CREATE INDEX idx_postings_account ON ledger_postings(account_id);
CREATE INDEX idx_postings_date ON ledger_postings(posting_date);
CREATE INDEX idx_postings_party ON ledger_postings(party_id);

-- ============================================================================
-- INVOICE <-> PAYMENT APPLICATION
-- ============================================================================

CREATE TABLE payment_allocations (
    allocation_id TEXT PRIMARY KEY,
    payment_transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
    invoice_transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
    amount_allocated NUMERIC NOT NULL,
    allocated_at TEXT NOT NULL
);

CREATE INDEX idx_allocations_payment ON payment_allocations(payment_transaction_id);
CREATE INDEX idx_allocations_invoice ON payment_allocations(invoice_transaction_id);

-- ============================================================================
-- ADVANCES TRACKING
-- ============================================================================

CREATE TABLE advances (
    advance_id TEXT PRIMARY KEY,
    party_id TEXT NOT NULL,
    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
    amount NUMERIC NOT NULL,
    amount_adjusted NUMERIC DEFAULT 0,
    gst_on_advance NUMERIC DEFAULT 0,
    is_fully_adjusted INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

-- ============================================================================
-- ATTACHMENTS REFERENCES
-- ============================================================================
-- Actual attachment bytes live under attachments/ in the zip; this table
-- tracks metadata and links to transactions.

CREATE TABLE attachment_refs (
    attachment_id TEXT PRIMARY KEY,
    transaction_id TEXT REFERENCES transactions(transaction_id),
    file_path TEXT NOT NULL,             -- relative path within the zip
    filename TEXT NOT NULL,
    mime_type TEXT,
    size_bytes INTEGER,
    sha256 TEXT,
    uploaded_at TEXT NOT NULL
);

-- ============================================================================
-- STOCK MOVEMENTS (if inventory enabled)
-- ============================================================================

CREATE TABLE stock_movements (
    movement_id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES items(item_id),
    transaction_id TEXT REFERENCES transactions(transaction_id),
    movement_date TEXT NOT NULL,
    quantity NUMERIC NOT NULL,           -- positive for in, negative for out
    rate NUMERIC,
    godown_id TEXT,
    batch_id TEXT,
    movement_type TEXT                   -- 'purchase', 'sale', 'transfer', 'adjustment', 'opening'
);

CREATE INDEX idx_stock_item ON stock_movements(item_id);
CREATE INDEX idx_stock_date ON stock_movements(movement_date);

-- ============================================================================
-- E-WAY BILLS
-- ============================================================================

CREATE TABLE eway_bills (
    ewb_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
    ewb_number TEXT,                     -- populated after portal generation
    transporter_name TEXT,
    transporter_id TEXT,
    vehicle_number TEXT,
    mode TEXT,                           -- 'road', 'rail', 'air', 'ship'
    distance_km INTEGER,
    reason TEXT,
    generated_at TEXT
);

-- ============================================================================
-- NOTES
-- ============================================================================
-- This schema is intentionally incomplete. The following are still TODO:
--   - CA annotation layer
--   - Journal voucher structure (covered by transactions/postings but may need specialized view)
--   - Budgets / forecasts (likely v2)
--   - Multi-currency support (v2)
--   - Custom fields / tags (v2)
--
-- The Bahi Phase 1 implementation will exercise this schema, identify gaps,
-- and the finalized DDL will replace this placeholder.
