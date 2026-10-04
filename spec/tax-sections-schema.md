# TDS and TCS sections — schema 2

`data/tds-sections/` and `data/tcs-sections/` hold one row per section per period. A rate or
threshold change is a new row with a new `validFrom`; the previous row gets a `validTo`. Rows are
never edited in place, so a payment is always computed with the values in force on its date.

The Income-tax Act, 2025 replaced the Income-tax Act, 1961 on 2026-04-01 and renumbered every
section. Rows carry the Act they belong to. A 1961 row whose section continues under the 2025 Act
names its `successor`, so an implementation holding an old section on a party (a vendor saved with
`194C`) resolves it to the right new section for a payment dated after the switch.

## Dataset file

```json
{
  "datasetVersion": "2026-10-04",
  "schema": "tds-sections/2",
  "description": "…",
  "publishedOn": "2026-10-04",
  "source": "…",
  "provenance": [ { "repo": "…", "path": "…", "commit": "…", "license": "…" } ],
  "license": "CC-BY-4.0 …",
  "entries": [ /* rows */ ]
}
```

## Row

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable identifier. 1961 Act: the section (`194C`, `194I(a)`). 2025 Act: the return code from the Income-tax Rules 2026 (`1023`), or the section reference when no code is published. |
| `act` | `"1961"` \| `"2025"` | The Act the row belongs to. |
| `section` | string | The section reference as written in the Act: `194C`, `393(1) Sl. 6(i)(a)`, `394(1) Sl. 4`. |
| `code` | string \| null | The 4-digit return code (2025 Act), null for 1961 rows. |
| `description` | string | What the section covers. |
| `rates` | object | Percent. TDS: `individual` (PAN fourth letter P or H), `other` (any other PAN holder), `noPan` (payee without a valid PAN). TCS: `standard`, `noPan`. A null rate means the section has no rate for that payee class; implementations fall back to the other class, and treat a section with no rate at all (salary, non-resident payments) as computed elsewhere. |
| `threshold` | object | Rupees. `single` (one payment or sale), `annual` (aggregate in the financial year), `note` (free text, e.g. "₹50,000 a month"). Null when none. |
| `validFrom` | ISO date | First day the row applies. |
| `validTo` | ISO date \| null | Last day it applies; null while in force. |
| `successor` | string \| object \| absent | 1961 rows only. The 2025 `id` that continues the section, or `{ "individual": "1023", "other": "1024" }` when the new Act splits it by payee. |
| `citation` | string \| absent | Present on rows from `data/overrides/`: the notification, Act section or circular that fixes the value. |

Periods for one `id` never overlap. A payment dated `d` uses the row with `validFrom ≤ d ≤ validTo`;
if the id has no such row and its last row ended before `d`, follow `successor`.

## Where the rows come from

`tools/sync_upstream.py` rebuilds both datasets from the open-source ERPs that maintain Indian tax
data, then applies `data/overrides/<dataset>.json` on top:

| Dataset | Primary | Fallback |
|---|---|---|
| tds-sections | india-compliance (ERPNext) `income_tax_india/data/tds_details.json`, `tds_details_old.json`, and its 2025-Act migration map | Odoo `l10n_in` tax templates (rates only; thresholds kept) |
| tcs-sections | Odoo `l10n_in` tax templates | the current dataset, unchanged |
| gst-rates | Odoo `l10n_in` (slab presence) | india-compliance tax defaults |
| hsn-full | india-compliance `gst_india/data/hsn_codes.json` | ERPNext v13 `regional/india/hsn_code_data.json` |

The GitHub workflow `sync-upstream.yml` runs weekly, primary first and fallback only when primary
fails, and opens a pull request; nothing reaches `main` without review. Overrides win over upstream,
and each override row cites the official source it was checked against. When upstream is wrong,
fix it in the overrides file, not by editing a published dataset.
