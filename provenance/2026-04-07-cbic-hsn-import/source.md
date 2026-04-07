# Source — CBIC HSN import on 2026-04-07

## Origin

- **Source URL:** https://cbic-gst.gov.in/gst-goods-services-rates.html
- **Source revision date (page "as on"):** 01.04.2023 (2023-04-01)
- **Scrape date:** 2026-04-07
- **Scraper:** `tools/scrape-cbic-hsn.py` v0.1
- **User-Agent used:** `khata-standard-scraper/0.1 (+https://github.com/NakliTechie/khata-standard)`

## Snapshot integrity

- **File:** `cbic-rate-schedule.html`
- **SHA-256:** `sha256:df64fd0823461623c63851a2fdd14b5a55953c3b9273cb074e100eae717f5d92`

The snapshot is preserved exactly as fetched. Do not reformat or edit it.
The hash above is the canonical record of what the CBIC page returned at
fetch time, and can be re-verified by running:

```
shasum -a 256 cbic-rate-schedule.html
```

## License and attribution

This dataset is sourced from the Central Board of Indirect Taxes and
Customs (CBIC) GST rate schedule under the
[Government Open Data License — India (GODL-India)](https://www.data.gov.in/Godl).

Data sourced from the Central Board of Indirect Taxes and Customs (CBIC)
GST rate schedule under GODL-India.

## Staleness disclosure

The CBIC rate schedule HTML page used as the source is dated
"as on 01.04.2023". GST Council decisions since that
date may have moved HSN codes between rate bands, introduced or
withdrawn cess on specific items, or otherwise altered the schedule.

The imported dataset is therefore marked `status: "starter"` rather than
`stable`. Implementations consuming this data should:

1. Treat the rate values as a reference baseline, not a current
   compliance source
2. Verify any HSN-specific rate against the latest GST Council
   notification before applying it to live tax calculations
3. Watch this repo for newer dated `hsn-common-*.json` files as the
   maintainer reruns the scraper after future Council meetings

## Known limitations

- The placeholder schema does not have a structured representation for
  compound or specific-rate compensation cess (e.g. "₹400 per tonne",
  "12% + ₹400 per 1000 sticks"). Cess rows are captured in a new
  `cessEntries` array with a free-text `cess` field; downstream
  consumers should treat this field as un-parsed.
- Conditional service rates that don't fit a standard band are listed
  in the dataset's `warnings` field rather than being silently dropped
  or forced into a wrong band.
- Some goods rows reference multiple HSN codes (e.g. "0202, 0203,
  0204"). The scraper expands these into one entry per HSN code,
  sharing the row's description and rate. This is the simplest shape
  for HSN→rate lookup at the cost of some duplicated description text.

## Related files

- `cbic-rate-schedule.html` — raw HTML snapshot of the source page
- `diff-summary.md` — counts and samples comparing this import to the
  prior placeholder
- `scraper-output.log` — stdout/stderr of the scraper run that produced
  this dataset

## Related datasets

- `data/hsn-common/hsn-common-20230401.json` — the
  imported dataset itself
- `data/gst-rates/gst-rates-20170701.json` — the rate-band definitions
  this import references via `rateId`
- `data/cess/cess-20250101.json` — the existing cess dataset; this
  import does not modify it
