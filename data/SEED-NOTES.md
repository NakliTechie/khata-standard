# Seed data notes — READ BEFORE USE

This directory is the initial seed for the `khata-standard` repo, produced at bootstrap. Everything here needs honest categorization before it's treated as production-ready. This file lists what's accurate, what's a reasonable starter, and what's a structural placeholder that absolutely must be replaced.

Status categories:

- **stable** — the data is accurate as of the published date and ready for production use
- **starter** — the data covers the most common cases and is factually correct for what it includes, but is not exhaustive; should be expanded over time
- **placeholder** — the data is a structural skeleton with illustrative examples only; must be replaced with sourced, authoritative data before production use

---

## states — STABLE

**File:** `data/states/states-20250101.json`

Full list of 28 Indian states + 8 union territories + the reserved "Other Territory" code. Each entry has:

- The 2-letter ISO 3166-2:IN code (canonical identifier)
- The 2-digit GSTIN state code (first two digits of every GSTIN)
- Official name
- Type (state / union_territory / other)

**Verification needed:** ISO codes follow ISO 3166-2:IN as of current revision. A few codes have seen revisions over time (e.g., `TG` vs `TS` for Telangana, `CT` vs `CG` for Chhattisgarh). Cross-reference against the ISO 3166-2:IN Wikipedia entry or official ISO publication before final commit. The GSTIN state codes are confident — verified from CBIC GST portal.

**Ready to use:** yes, with the verification above.

---

## gst-rates — STABLE

**File:** `data/gst-rates/gst-rates-20170701.json`

GST rate bands as they existed at launch on 1 July 2017. Seven bands: 0%, 0.25%, 3%, 5%, 12%, 18%, 28%. Each with validFrom/validTo dating, applicability notes, and rate type classification.

**Note:** These are only the rate *bands*. The mapping of individual HSN codes to rates is in `data/hsn/` and that's where the churn happens — GST Council rate changes almost always move specific HSNs between existing bands rather than introducing new bands.

**Ready to use:** yes.

**Future work:** add subsequent rate change files as the GST Council makes changes. Each change gets its own dated file (e.g., `gst-rates-20251001.json` for a hypothetical October 2025 rationalization).

---

## composition-rates — STABLE

**File:** `data/composition-rates/composition-rates-20250101.json`

The three composition scheme rates: 1% for traders/manufacturers, 5% for restaurants, 6% for service providers (introduced in 2019). Each with CGST/SGST split and applicability.

**Ready to use:** yes.

---

## coa-seed — STABLE

**File:** `data/coa-seed/coa-seed-20250101.json`

Standard Indian chart of accounts structure with five primary groups (Assets, Liabilities, Income, Expenses, System). Accounts are classified as essential (reserved by the application for specific posting logic) or optional (user can modify/delete). GST output/input parent accounts are seeded but sub-accounts per rate (e.g., "GST Output 18%") are created dynamically on first use, per the dynamic rate handling principle in the spec.

**Ready to use:** yes, but CAs may have opinions on the exact structure. Consider it a reasonable default rather than canonical.

---

## tds-sections — STARTER

**File:** `data/tds-sections/tds-sections-20250101.json`

Eight commonly-encountered TDS sections: 192, 194A, 194C, 194H, 194I, 194J, 194Q, 195. Each with description, threshold, rate(s), and date validity.

**Missing:** 193, 194 (dividends), 194B/BB (lottery/horse races), 194D/DA (insurance), 194E/EE/F/G/K/L/LA/LB/M/N/O/P/R/S, 196, 196A-D, and others. Rates and thresholds change annually with the Finance Act.

**Before use:** verify rates and thresholds against the current Finance Act. The rates shown are based on knowledge available at authoring time and may be stale.

---

## tcs-sections — STARTER

**File:** `data/tcs-sections/tcs-sections-20250101.json`

Four TCS sub-sections: 206C(1), 206C(1F), 206C(1G), 206C(1H). The most frequently encountered ones for SMB use, especially 206C(1H) which applies to sellers with turnover above ₹10 crore.

**Before use:** verify rates against current Finance Act. Section 206C(1G) in particular has been amended multiple times since introduction and the rate table here may not reflect current values.

---

## rcm-categories — STARTER

**File:** `data/rcm-categories/rcm-categories-20250101.json`

Twelve commonly-encountered RCM supply categories covering GTA, legal services, sponsorship, directors, insurance agents, recovery agents, security services, renting motor vehicles, import of services, copyright, arbitration, and government services.

**Missing:** less common specialized categories; Section 9(4) unregistered supplier scenario is noted but not enumerated.

**Before use:** verify against the latest consolidated CBIC notification, as RCM categories have been added and modified multiple times since 2017.

---

## challan-templates — STARTER

**File:** `data/challan-templates/challan-templates-20250101.json`

Nine challan form templates: ITNS 280, ITNS 281, ITNS 282, GST PMT-06, GST DRC-03, PF ECR, ESIC, Maharashtra PTRC, Maharashtra PTEC.

**Missing:** ITNS 283 (BCTT, effectively defunct), professional tax challans for other states (Karnataka, Tamil Nadu, West Bengal, Gujarat, Andhra Pradesh, Telangana, Kerala, etc.), Labour Welfare Fund challans by state, employees' compensation contributions, and other minor forms.

**Important:** the field definitions are structural and may need adjustment against the exact layout of the current official forms. Test against actual printed challans before Bahi ships the PDF generation for these.

---

## cess — STARTER

**File:** `data/cess/cess-20250101.json`

Six compensation cess entries covering tobacco, pan masala, aerated waters, small and large motor vehicles, and coal. Illustrative of the cess structure including compound rates (ad valorem + specific).

**Missing:** specific cess rates for the many categories of motor vehicles (SUV definitions, EV exclusions, etc.), detailed compound cess on tobacco products by length and filter type, and various other cessed items.

**Before use:** verify against the latest CBIC Compensation Cess (Rate) notification.

---

## hsn-common — PLACEHOLDER ⚠️

**File:** `data/hsn/hsn-common-20250101.json`

Ten illustrative HSN entries and five illustrative SAC entries covering common categories. This is a structural skeleton to unblock development, **not** a usable HSN reference.

**What a real release needs:** a curated top-2000 HSN code set covering ~95% of SMB transaction volume, with accurate rate assignments as of the current GST Council rate schedule.

**Sourcing options:**
1. Scrape the CBIC GST rate schedule from https://cbic-gst.gov.in/gst-goods-services-rates.html (public source, requires cleaning)
2. Purchase a compliance database from a commercial provider (costs money but is current)
3. Partner with an existing accounting tool that has already sourced and validated the list (potentially time-saving but requires a partnership)

**Bahi behavior until this is replaced:** flag unknown HSN codes as "not in bundled set" and prompt the user to enter the rate manually. The rate handling in §3.7 already supports this case because rates are looked up by (HSN, date) and an unknown lookup falls through to user input.

**Priority:** HIGH — this is the single biggest gap in the seed data and blocks real SMB use.

---

## sac — PLACEHOLDER ⚠️

**File:** `data/sac/sac-20250101.json`

Twelve major SAC category codes (all beginning with 99 under Indian classification). Covers the broad categories but not individual service sub-codes.

**What a real release needs:** the full SAC list from the CBIC service rate schedule, which includes specific codes for thousands of service types.

**Sourcing:** same options as HSN — scrape CBIC, purchase, or partner.

**Priority:** MEDIUM — service businesses need this but can work around with the broad category codes initially.

---

## What to do next

**Short term (before Bahi beta):**
1. Verify ISO 3166-2:IN codes in `states/` against authoritative source
2. Verify TDS/TCS section rates against current Finance Act
3. Test challan field definitions against actual official form PDFs
4. Start the work of sourcing HSN top-2000 (highest-impact gap)

**Medium term (before Bahi 1.0):**
1. Replace `hsn-common` placeholder with real data
2. Expand `sac` with specific service codes
3. Add professional tax challans for Karnataka, Tamil Nadu, West Bengal, Gujarat
4. Add Labour Welfare Fund challans by state
5. Add provenance documentation for each dataset (link to the CBIC notification or GST Council decision that authorized the current version)

**Ongoing:**
- Track GST Council meetings and publish rate change files within days of each meeting
- Track annual Finance Acts and update TDS/TCS rates
- Track CBIC notifications for new RCM categories
- Accept PRs from the community with proper provenance

---

## Honest statement for the repo README

Once the seed is committed, add this line to the repo README:

> **Current status:** the repo is bootstrapping. Several reference datasets are starter-quality or placeholder-quality (see `data/SEED-NOTES.md` for per-dataset classification). Do not use for real tax calculations until each dataset is marked `stable` in `index.json`.

This is honest, and honesty is the trust mechanism for a free tool.
