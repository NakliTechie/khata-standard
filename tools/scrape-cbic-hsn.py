#!/usr/bin/env python3
"""
scrape-cbic-hsn.py

Fetch the CBIC GST rate schedule HTML page, parse the embedded Goods and
Services rate tables, and emit a JSON dataset matching the schema used by
data/hsn-common/.

Usage:
    python tools/scrape-cbic-hsn.py [--dry-run] [--from-cache PATH]

Options:
    --dry-run         Fetch and parse but do not write the output file or
                      provenance directory. Print a summary instead.
    --from-cache PATH Skip the network fetch and parse a previously saved
                      HTML snapshot at PATH.

Output (default, non-dry-run):
    - data/hsn-common/hsn-common-<source-date>.json
    - provenance/<scrape-date>-cbic-hsn-import/
        source.md
        cbic-rate-schedule.html
        diff-summary.md
        scraper-output.log

Standard library only. No third-party dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional


SOURCE_URL = "https://cbic-gst.gov.in/gst-goods-services-rates.html"
USER_AGENT = (
    "khata-standard-scraper/0.1 "
    "(+https://github.com/NakliTechie/khata-standard)"
)
SCRAPER_VERSION = "0.1"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = REPO_ROOT / "tools" / "cache"
DEFAULT_CACHE_PATH = DEFAULT_CACHE_DIR / "cbic-rate-schedule.html"
HSN_COMMON_DIR = REPO_ROOT / "data" / "hsn-common"
PROVENANCE_DIR = REPO_ROOT / "provenance"
EXISTING_PLACEHOLDER = HSN_COMMON_DIR / "hsn-common-20250101.json"


# Map an IGST rate string to the rate ID defined in
# data/gst-rates/gst-rates-20170701.json. Returns None for rates that do
# not fit any standard band; the caller should treat those as warnings.
RATE_ID_BY_IGST = {
    "0": "gst-0-exempt",
    "0%": "gst-0-exempt",
    "nil": "gst-0-exempt",
    "exempt": "gst-0-exempt",
    "0.25": "gst-0-25-special",
    "0.25%": "gst-0-25-special",
    "3": "gst-3-precious",
    "3%": "gst-3-precious",
    "5": "gst-5-merit",
    "5%": "gst-5-merit",
    "12": "gst-12-standard-lower",
    "12%": "gst-12-standard-lower",
    "18": "gst-18-standard",
    "18%": "gst-18-standard",
    "28": "gst-28-demerit",
    "28%": "gst-28-demerit",
}


# ---------------------------------------------------------------------------
# Logging — captured to memory so the scraper can write a scraper-output.log
# alongside provenance.
# ---------------------------------------------------------------------------


class TeeLog:
    """Write log lines to stdout AND collect them in memory."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def log(self, msg: str) -> None:
        print(msg)
        self.lines.append(msg)

    def warn(self, msg: str) -> None:
        line = f"WARN: {msg}"
        print(line, file=sys.stderr)
        self.lines.append(line)

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def fetch_page(url: str, cache_path: Path, log: TeeLog) -> bytes:
    """Fetch the page with an identifying UA, save to cache, return bytes."""
    log.log(f"fetching {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status != 200:
                raise SystemExit(
                    f"error: fetch returned HTTP {resp.status} for {url}"
                )
            body = resp.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"error: HTTP {e.code} fetching {url}: {e.reason}")
    except urllib.error.URLError as e:
        raise SystemExit(f"error: network error fetching {url}: {e.reason}")
    log.log(f"fetched {len(body)} bytes")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(body)
    log.log(f"cached to {cache_path}")
    return body


def load_cached(path: Path, log: TeeLog) -> bytes:
    if not path.exists():
        raise SystemExit(f"error: cache file not found: {path}")
    body = path.read_bytes()
    log.log(f"loaded {len(body)} bytes from cache: {path}")
    return body


# ---------------------------------------------------------------------------
# HTML parsing — extract rows from <table id="goods_table"> and
# <table id="service_table">.
# ---------------------------------------------------------------------------


class TableRowsExtractor(HTMLParser):
    """Collect rows from a single <table id=target_id>.

    Rows are returned as a list of cells; each cell is the concatenated
    text content of all descendants (nested tables, <br>, &nbsp; etc. all
    flattened to plain text). This is intentionally lossy — the rate
    tables are flat enough that text is sufficient for parsing.
    """

    def __init__(self, target_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.target_id = target_id
        self.in_target = False
        self.target_depth = 0  # nested tables inside the target table
        self.in_row = False
        self.in_cell = False
        self.current_row: list[str] = []
        self.current_cell_parts: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            attr_dict = dict(attrs)
            if attr_dict.get("id") == self.target_id and not self.in_target:
                self.in_target = True
                self.target_depth = 1
                return
            if self.in_target:
                self.target_depth += 1
                return
        if not self.in_target:
            return
        if tag == "tr":
            self.in_row = True
            self.current_row = []
        elif tag == "td" or tag == "th":
            self.in_cell = True
            self.current_cell_parts = []
        elif tag == "br" and self.in_cell:
            self.current_cell_parts.append(" ")

    def handle_endtag(self, tag):
        if not self.in_target:
            return
        if tag == "table":
            self.target_depth -= 1
            if self.target_depth == 0:
                self.in_target = False
            return
        if tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = []
        elif tag in ("td", "th") and self.in_cell:
            text = "".join(self.current_cell_parts)
            text = unescape(text)
            text = re.sub(r"\s+", " ", text).strip()
            self.current_row.append(text)
            self.in_cell = False
            self.current_cell_parts = []

    def handle_data(self, data):
        if self.in_target and self.in_cell:
            self.current_cell_parts.append(data)


# ---------------------------------------------------------------------------
# Source-date extraction
# ---------------------------------------------------------------------------


AS_ON_PATTERNS = [
    re.compile(
        r"GST\s*rates?\s*for\s*Goods\s*and\s*Services\s*as\s*on\s*"
        r"(\d{1,2})\.(\d{1,2})\.(\d{4})",
        re.IGNORECASE,
    ),
    re.compile(
        r"as\s*on\s*(\d{1,2})\.(\d{1,2})\.(\d{4})",
        re.IGNORECASE,
    ),
]


def extract_source_date(html_text: str, log: TeeLog) -> date:
    for pat in AS_ON_PATTERNS:
        m = pat.search(html_text)
        if m:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            d = date(year, month, day)
            log.log(f'parsed source revision date "as on": {d.isoformat()}')
            return d
    raise SystemExit(
        "error: could not find an 'as on DD.MM.YYYY' marker on the page; "
        "the page structure may have changed and the scraper needs updating"
    )


# ---------------------------------------------------------------------------
# Goods table parsing
# ---------------------------------------------------------------------------


HSN_CODE_RE = re.compile(r"\b(\d{4,8}(?:\s\d{2,4})?)\b")


def split_hsn_cell(cell: str) -> list[str]:
    """Extract distinct HSN codes from a chapter/heading cell.

    Source cells take many shapes:
        "9503"
        "0202, 0203, 0204"
        "2106 90 20"
        "1404 or 3305"
        "0507 [Except 050790]"
        "0910 [other than 0910 11 10, 0910 30 10]"
        "5004 to 5006"

    Strategy: drop bracketed exclusion notes (including unbalanced
    brackets), expand "X to Y" ranges, then split on commas,
    semicolons, slashes, and the word "or", and keep chunks that look
    like HSN codes (digit-only, possibly with internal spaces for
    multi-segment tariff items).
    """
    if not cell:
        return []
    # Drop balanced bracketed exclusions, then strip lone brackets so a
    # cell like "[9003" still yields "9003".
    cell = re.sub(r"\[[^\]]*\]", " ", cell)
    cell = cell.replace("[", " ").replace("]", " ")

    out: list[str] = []

    def add(code: str) -> None:
        normalized = re.sub(r"\s+", " ", code).strip()
        if normalized and normalized not in out:
            out.append(normalized)

    # Expand inclusive ranges like "5004 to 5006" by replacing them
    # with the explicit list before splitting.
    def expand_range(match: "re.Match[str]") -> str:
        a = int(match.group(1))
        b = int(match.group(2))
        if b < a or b - a > 32:
            # implausibly large or inverted; leave the original text
            return match.group(0)
        return ", ".join(str(n) for n in range(a, b + 1))

    cell = re.sub(r"\b(\d{4})\s*to\s*(\d{4})\b", expand_range, cell)

    chunks = re.split(r"[,;/]|\bor\b", cell, flags=re.IGNORECASE)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"^(\d[\d\s]*\d|\d)$", chunk)
        if m:
            add(m.group(1))
    return out


def normalize_rate_text(text: str) -> str:
    return text.strip().lower().replace("\xa0", "").replace(" ", "")


def igst_to_rate_id(text: str) -> Optional[str]:
    return RATE_ID_BY_IGST.get(normalize_rate_text(text))


def parse_goods_table(
    html_text: str, source_date: date, log: TeeLog
) -> tuple[list[dict], list[dict], list[str]]:
    """Return (entries, cess_entries, warnings) from the goods table."""
    extractor = TableRowsExtractor("goods_table")
    extractor.feed(html_text)
    rows = extractor.rows
    log.log(f"goods_table: {len(rows)} raw rows")

    entries: list[dict] = []
    cess_entries: list[dict] = []
    warnings: list[str] = []

    # Schedule numeral → rate ID. Schedules I-V are the launch bands.
    # Schedule VI was added later for rough diamonds at 0.25%. Schedule VII
    # exists in the source for cut/polished diamonds at 1.5% but the launch
    # rate-bands file does not define a 1.5% band, so VII rows are routed
    # to warnings rather than mapped to a band that does not exist.
    schedule_to_rate_id = {
        "I": "gst-5-merit",
        "II": "gst-12-standard-lower",
        "III": "gst-18-standard",
        "IV": "gst-28-demerit",
        "V": "gst-3-precious",
        "VI": "gst-0-25-special",
    }

    seen_hsn: set[str] = set()
    rate_as_of = source_date.isoformat()

    for idx, row in enumerate(rows):
        if len(row) < 8:
            continue
        schedule = row[0].strip()
        sno = row[1].strip()
        hsn_cell = row[2].strip()
        description = row[3].strip()
        igst_cell = row[6].strip()
        cess_cell = row[7].strip() if len(row) > 7 else ""

        # Skip the column-header row
        if schedule.lower() == "schedules" and sno.lower().startswith("s."):
            continue
        # Skip explicitly-omitted rows (CBIC marks deleted entries this way
        # rather than removing them from the schedule). These have no HSN
        # and a description that is some flavour of "Omitted".
        if not hsn_cell and re.match(
            r"^\s*\[?\s*omitted", description, re.IGNORECASE
        ):
            continue

        if schedule.lower().startswith("compensation cess"):
            hsn_codes = split_hsn_cell(hsn_cell)
            if not hsn_codes:
                warnings.append(
                    f"goods row {idx} (cess sno {sno}): could not parse HSN "
                    f"from cell {hsn_cell!r}"
                )
                continue
            cess_text = cess_cell if cess_cell and cess_cell != "\xa0" else ""
            for hsn in hsn_codes:
                cess_entries.append(
                    {
                        "hsn": hsn,
                        "description": description,
                        "cess": cess_text,
                        "cessAsOf": rate_as_of,
                    }
                )
            continue

        rate_id = schedule_to_rate_id.get(schedule)
        if rate_id is None:
            # Try to recover from the IGST cell directly
            rate_id = igst_to_rate_id(igst_cell)
        if rate_id is None:
            warnings.append(
                f"goods row {idx} (sno {sno}, hsn {hsn_cell!r}, "
                f"schedule {schedule!r}, IGST {igst_cell!r}): no matching "
                f"rate band in data/gst-rates/gst-rates-20170701.json; "
                f"row skipped"
            )
            continue

        # Sanity-check: if schedule says one band but IGST cell says another,
        # log a warning but trust the schedule (the schedule column is the
        # authoritative grouping in the source).
        derived = igst_to_rate_id(igst_cell)
        if derived is not None and derived != rate_id:
            warnings.append(
                f"goods row {idx} (sno {sno}, hsn {hsn_cell!r}): "
                f"schedule {schedule} implies {rate_id} but IGST cell "
                f"{igst_cell!r} implies {derived}; using schedule"
            )

        hsn_codes = split_hsn_cell(hsn_cell)
        if not hsn_codes:
            warnings.append(
                f"goods row {idx} (sno {sno}): could not parse HSN from "
                f"cell {hsn_cell!r}"
            )
            continue

        for hsn in hsn_codes:
            key = f"{hsn}|{rate_id}"
            if key in seen_hsn:
                continue
            seen_hsn.add(key)
            entries.append(
                {
                    "hsn": hsn,
                    "description": description,
                    "rateId": rate_id,
                    "rateAsOf": rate_as_of,
                }
            )

    log.log(
        f"goods_table parsed: {len(entries)} entries, "
        f"{len(cess_entries)} cess entries, {len(warnings)} warnings"
    )
    return entries, cess_entries, warnings


# ---------------------------------------------------------------------------
# Service table parsing
# ---------------------------------------------------------------------------


SAC_CODE_RE = re.compile(
    r"\b(?:Heading|Group|Chapter|Section)\s*(\d{2,6})\b", re.IGNORECASE
)


def extract_sac_code(cell: str) -> Optional[str]:
    """Pull a numeric SAC heading/group/chapter from the cell, if any."""
    if not cell:
        return None
    m = SAC_CODE_RE.search(cell)
    if m:
        return m.group(1)
    # Sometimes the cell is just a bare number
    m = re.match(r"^\s*(\d{2,6})\b", cell)
    if m:
        return m.group(1)
    return None


def parse_service_table(
    html_text: str, source_date: date, log: TeeLog
) -> tuple[list[dict], list[str]]:
    extractor = TableRowsExtractor("service_table")
    extractor.feed(html_text)
    rows = extractor.rows
    log.log(f"service_table: {len(rows)} raw rows")

    entries: list[dict] = []
    warnings: list[str] = []
    rate_as_of = source_date.isoformat()
    seen: set[str] = set()

    for idx, row in enumerate(rows):
        if len(row) < 6:
            continue
        # Service table column layout: sno, chapter/section/heading,
        # description, cgst, sgst, igst, condition
        sno = row[0].strip()
        chapter_cell = row[1].strip()
        description = row[2].strip()
        igst_cell = row[5].strip() if len(row) >= 6 else ""

        # Skip the column-number legend row "(1) (2) (3) ..."
        if re.match(r"^\(\d+\)$", sno):
            continue

        rate_id = igst_to_rate_id(igst_cell)
        if rate_id is None:
            # Conditional rates like 0.75, 6, 7.5 do not fit standard bands
            # and section/chapter header rows have empty rate cells.
            if igst_cell and normalize_rate_text(igst_cell) not in ("", "&nbsp;"):
                warnings.append(
                    f"service row {idx} (sno {sno}): non-standard IGST rate "
                    f"{igst_cell!r} for {chapter_cell!r}; skipped"
                )
            continue

        sac = extract_sac_code(chapter_cell)
        if sac is None:
            warnings.append(
                f"service row {idx} (sno {sno}): could not extract SAC code "
                f"from {chapter_cell!r}"
            )
            continue

        key = f"{sac}|{rate_id}"
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "sac": sac,
                "description": description[:500],  # cap absurdly long entries
                "rateId": rate_id,
                "rateAsOf": rate_as_of,
            }
        )

    log.log(
        f"service_table parsed: {len(entries)} entries, "
        f"{len(warnings)} warnings"
    )
    return entries, warnings


# ---------------------------------------------------------------------------
# Output assembly
# ---------------------------------------------------------------------------


def build_dataset(
    source_date: date,
    scrape_date: date,
    entries: list[dict],
    cess_entries: list[dict],
    sac_entries: list[dict],
    warnings: list[str],
) -> dict:
    return {
        "datasetVersion": source_date.isoformat(),
        "description": (
            f"HSN/SAC codes from CBIC GST rate schedule, as on "
            f"{source_date.strftime('%d.%m.%Y')}. NOTE: this reflects a "
            f"snapshot over two years old; rates may not match current GST "
            f"Council decisions and require manual verification for current "
            f"compliance use."
        ),
        "publishedOn": scrape_date.isoformat(),
        "source": SOURCE_URL,
        "sourceRevision": source_date.isoformat(),
        "license": "GODL-India",
        "status": "starter",
        "notes": (
            "Imported via tools/scrape-cbic-hsn.py from the CBIC consolidated "
            "GST rate schedule HTML. Each goods row in the source is mapped "
            "to one entry per HSN code referenced in the row, sharing the "
            "row's description and rate. The 'cessEntries' field captures "
            "compensation cess rows separately because the placeholder schema "
            "does not have a structured representation for compound or "
            "specific-rate cess values; consumers should treat 'cess' as a "
            "free-text field for now. Service entries are limited to rows "
            "where a numeric SAC code can be extracted from the "
            "Chapter/Section/Heading cell AND the IGST rate maps to a "
            "standard band; conditional service rates (e.g. 0.75% on "
            "construction) are skipped and listed in 'warnings'. See the "
            "matching provenance/<scrape-date>-cbic-hsn-import/ directory "
            "for the full evidence trail."
        ),
        "entries": entries,
        "sacEntries": sac_entries,
        "cessEntries": cess_entries,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def write_provenance(
    provenance_dir: Path,
    source_date: date,
    scrape_date: date,
    raw_html: bytes,
    log_text: str,
    dataset: dict,
    placeholder_path: Path,
) -> None:
    provenance_dir.mkdir(parents=True, exist_ok=True)

    # Raw HTML snapshot
    snapshot_path = provenance_dir / "cbic-rate-schedule.html"
    snapshot_path.write_bytes(raw_html)
    snapshot_sha = hashlib.sha256(raw_html).hexdigest()

    # Diff summary vs the prior placeholder
    placeholder = json.loads(placeholder_path.read_text())
    prev_count = len(placeholder.get("entries", [])) + len(
        placeholder.get("sacPlaceholders", [])
    )
    new_goods = len(dataset["entries"])
    new_sac = len(dataset["sacEntries"])
    new_cess = len(dataset["cessEntries"])
    new_warnings = len(dataset["warnings"])

    # Rate-band distribution
    band_counts: dict[str, int] = {}
    for e in dataset["entries"]:
        band_counts[e["rateId"]] = band_counts.get(e["rateId"], 0) + 1
    band_lines = "\n".join(
        f"  - {band}: {count}" for band, count in sorted(band_counts.items())
    )

    # Sample entries (first 5 of each)
    sample_goods = "\n".join(
        f"  - {e['hsn']}: {e['description'][:80]} → {e['rateId']}"
        for e in dataset["entries"][:5]
    )
    sample_sac = "\n".join(
        f"  - {e['sac']}: {e['description'][:80]} → {e['rateId']}"
        for e in dataset["sacEntries"][:5]
    )

    diff_md = f"""# Diff summary — CBIC HSN import on {scrape_date.isoformat()}

## Counts

| | Previous (placeholder) | New (CBIC import) |
|---|---|---|
| Goods entries | {len(placeholder.get('entries', []))} | {new_goods} |
| SAC entries | {len(placeholder.get('sacPlaceholders', []))} | {new_sac} |
| Compensation cess entries | 0 | {new_cess} |
| Total | {prev_count} | {new_goods + new_sac + new_cess} |
| Warnings | n/a | {new_warnings} |

## Goods rate-band distribution (new dataset)

{band_lines if band_lines else '  (none)'}

## Sample goods entries

{sample_goods if sample_goods else '  (none)'}

## Sample SAC entries

{sample_sac if sample_sac else '  (none)'}

## Notes

- The previous placeholder was hand-curated and contained illustrative
  entries only. The new dataset is sourced from CBIC and is structurally
  much larger, but reflects the page's "as on {source_date.strftime('%d.%m.%Y')}"
  snapshot — over two years stale at the time of this import.
- Compensation cess rows are stored in a new `cessEntries` array because
  the existing schema cannot represent compound or specific-rate cess
  values. The `cess` field on each entry is a free-text capture of the
  raw cell content.
- Conditional service rates (e.g. 0.75% on construction services) are
  not mapped to standard bands and are listed in the dataset's
  `warnings` array; they should be revisited if the schema is later
  extended to support conditional rates.
"""
    (provenance_dir / "diff-summary.md").write_text(diff_md)

    # source.md
    source_md = f"""# Source — CBIC HSN import on {scrape_date.isoformat()}

## Origin

- **Source URL:** {SOURCE_URL}
- **Source revision date (page "as on"):** {source_date.strftime('%d.%m.%Y')} ({source_date.isoformat()})
- **Scrape date:** {scrape_date.isoformat()}
- **Scraper:** `tools/scrape-cbic-hsn.py` v{SCRAPER_VERSION}
- **User-Agent used:** `{USER_AGENT}`

## Snapshot integrity

- **File:** `cbic-rate-schedule.html`
- **SHA-256:** `sha256:{snapshot_sha}`

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
"as on {source_date.strftime('%d.%m.%Y')}". GST Council decisions since that
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

- `data/hsn-common/hsn-common-{source_date.strftime('%Y%m%d')}.json` — the
  imported dataset itself
- `data/gst-rates/gst-rates-20170701.json` — the rate-band definitions
  this import references via `rateId`
- `data/cess/cess-20250101.json` — the existing cess dataset; this
  import does not modify it
"""
    (provenance_dir / "source.md").write_text(source_md)

    (provenance_dir / "scraper-output.log").write_text(log_text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse but do not write the output file or provenance",
    )
    parser.add_argument(
        "--from-cache",
        type=Path,
        default=None,
        help="Parse a previously saved HTML file instead of fetching",
    )
    args = parser.parse_args(argv)

    log = TeeLog()
    scrape_date = datetime.now(timezone.utc).date()

    if args.from_cache:
        raw = load_cached(args.from_cache, log)
    else:
        raw = fetch_page(SOURCE_URL, DEFAULT_CACHE_PATH, log)

    html_text = raw.decode("utf-8", errors="replace")
    source_date = extract_source_date(html_text, log)

    goods_entries, cess_entries, goods_warnings = parse_goods_table(
        html_text, source_date, log
    )
    sac_entries, sac_warnings = parse_service_table(html_text, source_date, log)
    warnings = goods_warnings + sac_warnings

    dataset = build_dataset(
        source_date=source_date,
        scrape_date=scrape_date,
        entries=goods_entries,
        cess_entries=cess_entries,
        sac_entries=sac_entries,
        warnings=warnings,
    )

    out_filename = f"hsn-common-{source_date.strftime('%Y%m%d')}.json"
    out_path = HSN_COMMON_DIR / out_filename
    provenance_dir = (
        PROVENANCE_DIR / f"{scrape_date.isoformat()}-cbic-hsn-import"
    )

    log.log("")
    log.log("=== summary ===")
    log.log(f"goods entries: {len(goods_entries)}")
    log.log(f"sac entries:   {len(sac_entries)}")
    log.log(f"cess entries:  {len(cess_entries)}")
    log.log(f"warnings:      {len(warnings)}")
    log.log(f"output file:   {out_path}")
    log.log(f"provenance:    {provenance_dir}")

    if args.dry_run:
        log.log("dry-run: not writing output or provenance")
        return 0

    HSN_COMMON_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n")
    log.log(f"wrote {out_path}")

    write_provenance(
        provenance_dir=provenance_dir,
        source_date=source_date,
        scrape_date=scrape_date,
        raw_html=raw,
        log_text=log.text(),
        dataset=dataset,
        placeholder_path=EXISTING_PLACEHOLDER,
    )
    log.log(f"wrote provenance to {provenance_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
