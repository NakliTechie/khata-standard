# GST 2.0 rates and the tobacco cutover — 2026-10-04

Official sources, downloaded from taxinformation.cbic.gov.in (the notification store; `cbic-download.sh`
shows how: an anonymous token from `/api/authenticate-token`, then `/api/cbic-notification-msts/download/<id>/ENG`).
The `.txt` files are `pdftotext -layout` output of the PDFs.

| Notification | Store id | Date | In force | Effect |
|---|---|---|---|---|
| 9/2025-Central Tax (Rate) | 1010436 (corrigendum 1010467) | 2025-09-17 | 2025-09-22 | Supersedes 1/2017. Schedules I 5%, II 18%, III 40%, IV 3%, V 0.25%, VI 1.5%, VII 28% (pan masala and tobacco only). |
| 19/2025-Central Tax (Rate) | 1010534 | 2025-12-31 | 2026-02-01 | Biris into Schedule II (18%); pan masala and tobacco into Schedule III (40%); Schedule VII omitted. |
| 03/2025-Compensation Cess (Rate) | 1010537 | 2025-12-31 | 2026-02-01 | Compensation cess Nil on the tobacco entries. |
| 02/2025-Compensation Cess (Rate) | 1010449 | 2025-09-17 | 2025-09-22 | Compensation cess Nil on other goods. |
| 14/2025-Central Tax (Rate) | — | 2025 | — | Bricks and tiles at 6% CGST (12% GST): the 12% band stays open. |

Datasets built from them:
- `data/hsn-common/hsn-common-20260201.json` — `tools/parse_rate_notification.py`. 1,195 rows of 9/2025 and 7 of 19/2025 parsed (every serial number in every schedule accounted for); 1,295 codes; 123 conditional (listed at more than one rate, or chapter-level).
- `data/gst-rates/gst-rates-20261004.json` — via `data/overrides/gst-rates.json`: 40% from 2025-09-22; 28% ends 2026-01-31; 12% stays.
- `data/cess/cess-20260201.json` — tobacco entries end 2026-01-31.

Not parsed yet: nil-rated goods (10/2025), services changes (15/2025, except GTA's 12% → 18% applied by hand).
Cross-checked against PIB release PRID 2163555 (the GST Council's 56th meeting change list).
