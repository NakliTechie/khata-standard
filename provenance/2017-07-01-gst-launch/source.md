# Source — GST launch rate bands (1 July 2017)

## Effective date

1 July 2017

## What changed

This is the initial provenance entry for the GST rate bands as they existed when the Goods and Services Tax was introduced in India on 1 July 2017. It documents the source of the `gst-rates-20170701.json` reference dataset in this repository.

Seven rate bands were introduced at launch:

- 0% (exempt / nil-rated)
- 0.25% (rough precious stones)
- 3% (gold and precious metals)
- 5% (merit rate)
- 12% (lower standard rate)
- 18% (standard rate)
- 28% (demerit rate)

Additionally, a compensation cess was levied on specified luxury and sin goods in addition to the 28% rate.

## Sources

### Primary legislative source

- **Central Goods and Services Tax Act, 2017** (CGST Act)
  - Enacted: 12 April 2017
  - Commenced: 1 July 2017
  - [PRS India — CGST Act overview](https://prsindia.org/billtrack/the-central-goods-and-services-tax-bill-2017)
  - Official text on [India Code](https://www.indiacode.nic.in/handle/123456789/2074)

### Rate notifications

- **CBIC Notification No. 1/2017-Central Tax (Rate), dated 28 June 2017**
  - Title: "Seeks to notify the rates of central tax on supply of goods"
  - Published in the Gazette of India, Extraordinary, Part II, Section 3, Sub-section (i)
  - Companion notifications issued under SGST and IGST Acts

- **CBIC Notification No. 2/2017-Central Tax (Rate), dated 28 June 2017**
  - Title: "Seeks to notify the exempted goods under GST"

- **CBIC Notification No. 11/2017-Central Tax (Rate), dated 28 June 2017**
  - Title: "Seeks to notify the rates for supply of services under CGST Act"

- **CBIC Notification No. 12/2017-Central Tax (Rate), dated 28 June 2017**
  - Title: "Seeks to notify the exemptions on supply of services under CGST Act"

### GST Council decisions

The rate structure was recommended by the GST Council at multiple meetings in 2016 and 2017. Key meetings:

- **14th GST Council Meeting** (18-19 May 2017, Srinagar) — finalized rate schedules for goods
- **15th GST Council Meeting** (3 June 2017, New Delhi) — finalized rate schedules for services and residual items
- **16th GST Council Meeting** (11 June 2017, New Delhi) — final review and minor adjustments before rollout

GST Council meeting minutes and press releases are available at: https://gstcouncil.gov.in/gst-council-meetings

### Official rate schedule reference

The current consolidated rate schedule (post-launch updates included) is maintained by CBIC at:

- https://cbic-gst.gov.in/gst-goods-services-rates.html

Note: this URL shows the *current* rates, not the rates as they were at launch. Historical rate tracking requires archiving previous versions of this page or cross-referencing against dated notifications.

## Archived documents

The `notification.pdf` file in this directory is a placeholder. A real archive should include:

- Notification 1/2017-Central Tax (Rate) — PDF from the Gazette of India
- Notification 11/2017-Central Tax (Rate) — PDF from the Gazette of India
- Excerpts from the relevant GST Council meeting minutes

If you have access to these official PDFs, please open a PR to add them to this directory. Archived official documents protect the provenance trail from link rot on government websites.

## Notes for backfill

This provenance entry was created during repository bootstrap and is retroactive — the rate data itself was compiled from publicly-available sources at the time of this repo's creation, not authoritatively traced back to the original 2017 notifications. Backfilling the actual 2017 PDFs would strengthen the trail.

## Related datasets

- `data/gst-rates/gst-rates-20170701.json` — the rate bands themselves
- `data/hsn-common/hsn-common-20250101.json` — HSN-to-rate assignments (placeholder; real HSN rate mapping pending)
- `data/cess/cess-20250101.json` — compensation cess applied alongside the 28% rate on specified items
