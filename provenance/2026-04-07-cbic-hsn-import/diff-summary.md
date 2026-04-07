# Diff summary — CBIC HSN import on 2026-04-07

## Counts

| | Previous (placeholder) | New (CBIC import) |
|---|---|---|
| Goods entries | 10 | 1518 |
| SAC entries | 5 | 82 |
| Compensation cess entries | 0 | 78 |
| Total | 15 | 1678 |
| Warnings | n/a | 39 |

## Goods rate-band distribution (new dataset)

  - gst-0-25-special: 3
  - gst-0-exempt: 172
  - gst-12-standard-lower: 278
  - gst-18-standard: 692
  - gst-28-demerit: 36
  - gst-3-precious: 15
  - gst-5-merit: 322

## Sample goods entries

  - 0202: All goods [other than fresh or chilled] pre-packaged and labelled. → gst-5-merit
  - 0203: All goods [other than fresh or chilled] pre-packaged and labelled. → gst-5-merit
  - 0204: All goods [other than fresh or chilled] pre-packaged and labelled. → gst-5-merit
  - 0205: All goods [other than fresh or chilled] pre-packaged and labelled. → gst-5-merit
  - 0206: All goods [other than fresh or chilled] pre-packaged and labelled. → gst-5-merit

## Sample SAC entries

  - 9954: (ie) Construction of an apartment in an ongoing project under any of the schemes → gst-12-standard-lower
  - 9954: (if) Construction of a complex, building, civil structure or a part thereof, inc → gst-18-standard
  - 9954: (xi) Services by way of house-keeping, such as plumbing, carpentering, etc. wher → gst-5-merit
  - 9961: Services in wholesale trade. Explanation-This service does not include sale or p → gst-18-standard
  - 9962: Services in retail trade. Explanation- This service does not include sale or pur → gst-18-standard

## Notes

- The previous placeholder was hand-curated and contained illustrative
  entries only. The new dataset is sourced from CBIC and is structurally
  much larger, but reflects the page's "as on 01.04.2023"
  snapshot — over two years stale at the time of this import.
- Compensation cess rows are stored in a new `cessEntries` array because
  the existing schema cannot represent compound or specific-rate cess
  values. The `cess` field on each entry is a free-text capture of the
  raw cell content.
- Conditional service rates (e.g. 0.75% on construction services) are
  not mapped to standard bands and are listed in the dataset's
  `warnings` array; they should be revisited if the schema is later
  extended to support conditional rates.
