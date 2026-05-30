# Compensation-cess reference-data schema

**Part of:** `.khata` reference-data specification
**Status:** draft, will freeze at format version 1.0
**Last revised:** 2026-05-30 — structured schema locked (replaces the free-text `cess` field).

---

## Purpose

GST compensation cess is levied *in addition to* GST on a small set of luxury / sin goods (tobacco, aerated waters, motor vehicles, coal). Unlike the seven GST rate bands, cess does not reduce to a single ad-valorem percentage: a rate may be **ad valorem**, a **specific** per-unit amount, a **compound** of both, or **conditional** on a sub-classification the HSN code does not capture.

The April 2023 CBIC import originally captured these as a free-text `cess` string. That is enough to *display* to a user but not to *compute* cess on an invoice line. This document defines the structured shape so any implementation can compute cess where it is determinate, and fall back to manual entry where it is not.

This schema governs the cess reference dataset at `data/cess/` (e.g. `data/cess/cess-20250922.json`).

---

## Entry shape

Each dataset entry is a JSON object:

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `cessId` | string | yes | Stable identifier for the entry. |
| `description` | string | yes | Human-readable description of the goods. |
| `hsnPattern` | string | yes | HSN prefix the entry matches. Whitespace is insignificant (`"2106 90 20"` == `"21069020"`). Matching is by **prefix**, longest match wins (see "Lookup"). |
| `cessType` | enum | yes | One of `ad_valorem`, `specific`, `compound`, `conditional`. |
| `cessRate` | number \| null | yes | The ad-valorem **percentage** (e.g. `12.0` = 12%) when the entry has a single determinate ad-valorem rate; `null` otherwise. |
| `specific` | object \| absent | when applicable | A determinate per-unit component: `{ "amount": <number>, "currency": "INR", "unit": <string> }`. Present for `specific` (and computable `compound`) entries. |
| `raw` | string | yes | The **verbatim source text** of the rate, so the structured fields can be audited against the notification. |
| `autoApplicable` | boolean | yes | `true` iff the cess can be computed from HSN + date + the line's value/quantity alone. `false` when it depends on criteria not encoded in the HSN. |
| `validFrom` | date | yes | First date the entry applies (`YYYY-MM-DD`). |
| `validTo` | date \| null | yes | Last date the entry applies, or `null` for open-ended. Used for effective-dated lifecycle (e.g. the 2025-09-22 GST 2.0 discontinuation sets `validTo: "2025-09-21"` on non-tobacco entries). |
| `note` | string | no | Human context / caveats. |

### `cessType` cases

- **`ad_valorem`** — a percentage of the taxable value. `cessRate` carries the percent; `specific` is absent. *Example: aerated waters 12%, pan masala 60%.*
- **`specific`** — a fixed amount per unit of quantity. `cessRate` is `null`; `specific` carries `{amount, currency, unit}`. *Example: coal ₹400 per tonne.*
- **`compound`** — both an ad-valorem and a specific component apply additively. When both are determinate, `cessRate` carries the percent and `specific` the per-unit amount. When the components vary by sub-classification (e.g. cigarettes by stick length / filter), set `cessRate: null`, omit `specific`, and `autoApplicable: false`.
- **`conditional`** — the rate depends on criteria the HSN does not encode (e.g. motor vehicles 1%–22% by engine capacity, length, fuel type, SUV/luxury category). `cessRate: null`, `autoApplicable: false`; the `raw` text describes the brackets.

### Computation

For an `autoApplicable` entry, on a line with taxable value `T` (in the smallest currency unit, e.g. paise) and quantity `Q`:

```
advalorem component = round(T * cessRate / 100)      # when cessRate != null
specific   component = round(Q * specific.amount * <currency-minor-units>)   # when specific present, units reconciled
cess = advalorem component + specific component
```

The consuming application MUST reconcile the line's unit of measure with `specific.unit` before applying a specific component, and SHOULD surface `autoApplicable: false` entries to the user for manual entry rather than guessing a rate.

---

## Lookup

A cess entry's `hsnPattern` applies to that HSN heading **and all of its sub-codes**: an item HSN `22021010` is matched by the `2202` entry. When multiple entries match, the **longest** `hsnPattern` wins (most specific). The match is then filtered by date: the entry applies only when `validFrom <= invoiceDate <= validTo` (treating `validTo: null` as open-ended). This mirrors the GST-rate lifecycle, so a historical invoice always resolves the rate that was in force on its date and is never re-stated when the schedule changes.

---

## Backward compatibility

The flat fields `cessType`, `cessRate`, `hsnPattern`, `validFrom`, and `validTo` are the minimum a consumer needs to look up and apply an ad-valorem cess. A consumer that ignores `specific`, `raw`, and `autoApplicable` still resolves ad-valorem cess correctly; those fields only *add* machine-readable detail for specific/compound goods and provenance. The reference implementation (Bahi) reads exactly the flat fields and treats `cessRate: null` as "no auto-cess," which is the safe behaviour for every non-`ad_valorem` entry.

---

## Status and future work

The entry shape is **locked** and applied to `data/cess/cess-20250922.json`. Remaining before the 1.0 freeze:

- Migrate the ~78 free-text cess rows captured in `data/hsn-common/hsn-common-20230401.json` from their original `cess` string into this structured shape (tracked separately).
- Confirm the exact CBIC notification + cutover date for the 2025-09-22 GST 2.0 discontinuation.
