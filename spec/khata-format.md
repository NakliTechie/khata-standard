# `.khata` file format specification

**Version:** 1.0 (draft)
**Status:** draft — will be frozen at 1.0 once the first reference implementation (Bahi) reaches beta
**Changes:** tracked version-by-version in [CHANGELOG.md](CHANGELOG.md)
**Last revised:** 2026-05-30 — file structure, manifest fields, and `books.sqlite` table list aligned with the reference implementation (schema 12).

---

## Overview

A `.khata` file is a portable container for a single Indian business's accounting records — invoices, purchases, ledger, masters, GST data, attachments, and audit history. The format is designed to be:

- **Local-first** — the file lives on the user's disk, not on a server
- **Self-contained** — everything needed to read the books is in the file
- **Portable** — any compatible application can open the file
- **Auditable** — every change is logged with cryptographic integrity
- **Open** — the format is public and anyone can implement it

This document is the authoritative specification. Reference implementations (including Bahi) must conform to this spec; user-facing tool specs may add their own behavior on top, but the file format itself is defined here.

---

## File structure

A `.khata` file is a standard ZIP archive with the extension `.khata`. Any ZIP tool can open it. The contents:

```
mybooks.khata
├── manifest.json          # identity, schema version, integrity (hashes + signing key)
├── books.sqlite           # the double-entry ledger AND the append-only audit log
├── snapshots/             # rolling in-file save snapshots (crash / corruption recovery)
├── attachments/           # user-uploaded supporting documents (scanned bills, etc.)
└── exports/               # cached report exports (optional)
```

The minimum required files are `manifest.json` and `books.sqlite`. The `snapshots/`, `attachments/`, and `exports/` directories are optional.

---

## manifest.json

The manifest is the entry point and must exist at the root of the archive. It contains:

- `khataFormatVersion` — the format spec version this file conforms to (e.g., `"1.0"`)
- `schemaVersion` — the internal `books.sqlite` schema version (e.g., `12`)
- `workspaceId` — stable per-file identifier (UUID)
- `createdAt` / `lastModifiedAt` — ISO 8601 timestamps
- `company` — current company identity fields, with a `changeHistory` rename trail
- `uiTier` — progressive-unlock UI tier
- `snapshots` — metadata for the in-file save snapshots
- `integrity` — `booksHash` (database bytes), `auditHead` (audit-chain head), `signedBy` (signing public key, JWK)
- `modeHistory` — record of when this file was opened in Owner vs CA mode

The audit log itself lives in `books.sqlite` (the `audit_log` table), **not** the manifest; the manifest only mirrors its head hash in `integrity.auditHead`. See `manifest.schema.json` in this directory for the full JSON Schema.

### Canonical state representation

All state references throughout the file (company state, customer addresses, vendor addresses, place of supply) use **2-letter ISO 3166-2:IN subdivision codes** (e.g., `MH`, `DL`, `KA`). The 2-letter code is the canonical key. GSTIN numeric state codes and human-readable state names are stored alongside as denormalized convenience fields, but the ISO code is the source of truth.

This is a forward-compatibility decision: the ISO code is internationally standardized and does not embed India-specific GST numbering assumptions.

---

## books.sqlite

A standard SQLite database containing the accounting records. The schema is defined in `books-schema.sql` in this directory.

Key tables (partial list, full DDL in the schema file):

- `accounts` — chart of accounts
- `entries` / `entry_lines` — the double-entry ledger (every posting)
- `invoices` / `invoice_lines`, `purchases` / `purchase_lines` — sales and purchase documents
- `customers`, `vendors`, `items` — masters
- `stock_movements`, `batches` — inventory (Weighted Average Cost + FIFO)
- `audit_log` — the append-only, hash-chained audit log (see `audit-log.md`)

Each posted document carries its own immutable reference-data snapshots as columns (e.g. `company_snapshot` / `customer_snapshot` JSON on `invoices`; literal `tax_rate` and `cess` on each line) rather than in separate snapshot tables.

### Historical integrity principle

Every posted transaction captures a snapshot of the reference data fields relevant to that transaction at the time of posting. Reference data (company profile, tax rates, HSN descriptions, master records) is allowed to change, but those changes never reach backward into already-posted transactions. A reprinted invoice always shows the company name, tax rates, and customer details as they were when the invoice was originally issued.

This applies to:
- Company identity (name, address, GSTIN, PAN, logo reference)
- Tax rates (the literal percentage value is stored on each taxable line)
- HSN/SAC codes and their descriptions
- State names (as they were at posting time)
- Customer/vendor fields appearing on the document (name, address, GSTIN)

See `audit-log.md` for how changes to reference data are recorded without altering historical postings.

---

## Audit log

Every state-changing action appends an entry to the `audit_log` table in `books.sqlite`. The log is:

- **Append-only** — entries are never deleted or modified
- **Hash-chained** — each entry's hash covers the previous entry's hash (a versioned preimage), making tampering detectable
- **Signed** — each entry's hash may be signed by a keypair that can be rotated (rotations themselves are logged)

The manifest mirrors the chain head in `integrity.auditHead` and the signing key in `integrity.signedBy`. See `audit-log.md` for the detailed specification, including the canonical-JSON rules and test vectors.

---

## Versioning policy

The format follows semantic versioning:

- **Patch version** (1.0.x) — clarifications, editorial improvements, no schema changes
- **Minor version** (1.x) — backward-compatible additions (new optional fields, new optional tables)
- **Major version** (x.0) — backward-incompatible changes (requires migration)

A reader should:
- **Open files with the same major version** — guaranteed to work
- **Open files with older minor versions within the same major** — works, unknown fields are preserved if the reader writes back
- **Open files with newer minor versions within the same major** — works in read-only mode; writing requires matching or newer reader version to avoid data loss
- **Open files with different major versions** — may refuse, should warn and offer read-only inspection

Bahi's implementation of these rules is documented in the Bahi spec §10.18.

---

## Reference data

Reference data (HSN codes, GST rates, state list, TDS sections, etc.) is NOT stored in the `.khata` file. It lives in the `khata-standard` repository under `data/` and is distributed via the CDN at `https://naklitechie.github.io/khata-standard/data/` (SHA-256 verified per dataset against `data/index.json`). Applications fetch reference data on demand (user-initiated) and cache it locally.

The rationale: reference data changes over time and is not specific to any one company's books. Embedding it in every `.khata` file would bloat files unnecessarily and make updates impossible without re-writing every file.

See `data/SEED-NOTES.md` in this repo for current reference data status.

---

## Licensing

The format specification itself is licensed under MIT. Anyone is free to implement `.khata` readers or writers without permission or royalty. The reference data in `data/` is licensed under CC-BY 4.0.

---

## Current status

This is a **draft** specification. The first reference implementation (Bahi) is under active development. Version 1.0 will be frozen when Bahi reaches beta and the spec has been exercised against real usage.

Until 1.0 is frozen, expect clarifications and minor additions. Backward-incompatible changes will be avoided, but not yet guaranteed.

## Contributing

See `CONTRIBUTING.md` at the repo root.
