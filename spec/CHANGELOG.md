# Changelog — `.khata` specification

All notable changes to the `spec/` documents (and the reference data shapes they
govern) are recorded here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/). The spec is **pre-1.0** and moves
in dated draft revisions; format version **1.0** will be frozen once the reference
implementation (Bahi) reaches beta and the spec has been exercised against real usage.

Each spec file also carries a `**Last revised:**` line in its header pointing back here.

---

## 1.0-draft

### 2026-10-04 — tax-section schema 2, the Income-tax Act 2025, GST 2.0 rates; upstream sync

**`tax-sections-schema.md`** (new) — TDS and TCS rows are effective-dated, one per section per period, with the Act they belong to (`1961` or `2025`), the 2025-Act return code, rates per payee class (`individual` / `other` / `noPan`, percent) and thresholds (`single` / `annual` / `note`, rupees). A 1961 row names its `successor`, so a party saved with `194C` resolves to `1023` or `1024` after 2026-04-01. Replaces the schema-1 `sections` shape.

Data, all new files (the old ones stay for apps that pinned them):
- `tds-sections-20261004.json` — 1961-Act rows to 2026-03-31 and Income-tax Act 2025 rows (392/393) from 2026-04-01. Corrections over upstream: 194H 5% → 2% on 2024-10-01; rent thresholds monthly from FY 2025-26; the single `194J` kept for older books.
- `tcs-sections-20261004.json` — 206C rows to 2026-03-31 (206C(1H) ended 2025-03-31) and section 394 rows from 2026-04-01 at the Finance Act 2026 rates.
- `gst-rates-20261004.json` — the 40% band from 2025-09-22; 28% ends 2026-01-31; 12% stays (bricks and tiles). Uses the rate ids implementations already store (`gst-18`, …).
- `hsn-common-20260201.json` (schema `hsn-common/2`) — per-HSN rate histories from Notifications 9/2025 and 19/2025.
- `hsn-full-20261004.json` (first publication) — 18,687 HSN codes with descriptions.
- `cess-20260201.json` — compensation cess on pan masala and tobacco ends 2026-01-31.

**Tools** — `tools/sync_upstream.py` and the `sync-upstream.yml` workflow (primary, fallback, alert; opens a PR), and `tools/parse_rate_notification.py`.

### 2026-05-30 — spec aligned to the reference implementation (schema 12)

Now that Bahi exercises the format at scale, the spec tracks its actual output rather than a parallel abstract model — simpler and clearer for any implementer. *(Resolves #3 and #4.)*

- **`books-schema.sql`** — replaced the abstract `transactions`/`transaction_lines` skeleton with the reference implementation's real **schema 12** DDL (35 tables; INTEGER paise; `audit_log` with `hash_version`; header + per-line `cess`; document-level reference-data snapshots as columns). Loads cleanly in SQLite.
- **`manifest.schema.json`** — rewritten to validate the reference implementation's real `manifest.json`: top-level `workspaceId` / `uiTier` / `snapshots`; `company` with snake_case fields + `changeHistory`; `integrity` with `booksHash` + `auditHead` (bare 64-hex) + `signedBy` as a **JWK object**. Removed the `auditLog` / `invoiceSeries` / `periodLocks` / `financialYears` manifest arrays — those live in `books.sqlite`. Validated against a real generated manifest.
- **`khata-format.md`** — file structure (added `snapshots/`), manifest field list, and `books.sqlite` key-table list updated to match; the audit log is documented in the `audit_log` table rather than the manifest; CDN URL corrected to the GitHub Pages endpoint.
- **`audit-log.md`** — Storage simplified to the single actual model: the `audit_log` table in `books.sqlite`, with the manifest mirroring `auditHead` + `signedBy`.

### 2026-05-30 — audit-log hash chain locked; structured compensation-cess schema

**`audit-log.md`** — the hash chain is now locked and test-vector-backed.
- **Canonical-JSON rules locked**: recursively sort object keys by UTF-16 code unit; serialize primitives as `JSON.stringify` does (non-ASCII NOT `\u`-escaped); no insignificant whitespace; array order preserved.
- **Versioned hash preimage** (`hash_version`): `2` (current) hashes the chain link plus every semantic field — `canonicalJson({v, prev, ts, actor, action, ref, origin, payload})`; `1`/absent is the legacy `prev + origin + payload` scheme, kept verify-only. Replaces the previous single "hash the whole entry" definition, which matched no shipping implementation.
- **Hash format**: 64 lowercase hex characters, **no `sha256:` prefix** (was prefixed).
- **Storage** reconciled: an implementation MAY hold the log in a `books.sqlite` `audit_log` table (what the reference implementation does) or a `manifest.json` array; the manifest always carries the chain head + signing key.
- **Signing** reconciled to the reference implementation: per-entry ECDSA P-256 signature over the entry `hash`, public key (JWK) in `manifest.integrity.signedBy`.
- **Added `hash_version` and `payload`/`prev_hash` to the entry field list.**

**`audit-log-test-vectors.json`** (new) — byte-exact `(canonical bytes → hash)` vectors for the canonical-JSON rules, the v1 and v2 preimages, and a golden 4-entry chain drawn from a generated sample. Any implementation that reproduces these will verify chains written by the reference implementation. *(Resolves issue #5 items 2 — canonical JSON rules — and 3 — test vectors.)*

**`cess-schema.md`** (new) — structured compensation-cess reference-data schema.
- `cessType`: `ad_valorem | specific | compound | conditional`; `cessRate` (ad-valorem percent or null); `specific {amount, currency, unit}`; `raw` (verbatim source text); `autoApplicable`; effective-dated `validFrom`/`validTo`; prefix-match `hsnPattern`.
- Replaces the free-text `cess` field as the computable shape. *(Resolves the design ask in issue #18; the ~78 `hsn-common` free-text rows remain to be migrated — tracked separately.)*

**`data/cess/cess-20250922.json`** — reconciled to the structured schema (added `specific`, `raw`, `autoApplicable`; `cessNote` folded into `raw`). Back-compatible: consumers that read only the flat fields (`cessType`, `cessRate`, `hsnPattern`, `validFrom`, `validTo`) are unaffected.

**`books-schema.sql`** — added the `audit_log` table (with `hash_version`) so the schema reflects the reference implementation's audit storage; linked the `cess_total` / `cess_rate` / `cess_amount` columns to `cess-schema.md`; updated design principle #5 (audit log MAY live in `books.sqlite`).

### 2025-09-22 — compensation-cess GST 2.0 discontinuation *(data)*
- `data/cess/cess-20250922.json` published: under GST 2.0 the compensation cess was discontinued for all goods except the tobacco family with effect from 2025-09-22; non-tobacco entries carry `validTo: "2025-09-21"`, and the two ambiguous 8703 motor-vehicle entries were consolidated into one non-auto-applicable entry. Provenance under `data/` + dataset notes.

### 2026-04-07 — 1.0-draft baseline
- Initial `spec/` captured during repo bootstrap: `khata-format.md`, `manifest.schema.json`, `books-schema.sql`, `audit-log.md`.
- `audit-log.md` later (commit `9bdd601`) added the `ai` actor value + optional `aiAssisted` field.
