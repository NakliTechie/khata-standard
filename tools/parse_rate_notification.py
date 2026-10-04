#!/usr/bin/env python3
"""
parse_rate_notification.py

Build hsn-common (schema 2) from the text of the CBIC goods-rate notifications, the only official
source of HSN-wise GST rates since cbic-gst.gov.in emptied its rate tables.

    python tools/parse_rate_notification.py --n9 n09.txt --n19 n19.txt [--previous data/hsn-common/hsn-common-20230401.json]

Inputs are the PDFs' text (pdftotext -layout), archived under provenance/<date>-gst-2-0-rates/:
    9/2025-Central Tax (Rate), 17 Sep 2025, in force 2025-09-22: the seven goods schedules.
    19/2025-Central Tax (Rate), 31 Dec 2025, in force 2026-02-01: biris into Schedule II, pan masala
        and tobacco into Schedule III, Schedule VII (28%) omitted.

Each tariff code gets a rate history: the previous dataset's rate up to 2025-09-21 (where it had
one), then 9/2025's from 2025-09-22, then 19/2025's from 2026-02-01 where that changed it. A code
listed under two schedules (a value test such as apparel above or below ₹2,500 a piece) is marked
`conditional` with both candidates and no automatic rate, so an app never guesses.

Nil-rated goods live in 10/2025 and are not parsed here; their codes simply have no post-2025-09-22
rate. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

GST2_FROM, GST2_TO_PREV = "2025-09-22", "2025-09-21"
N19_FROM, N19_TO_PREV = "2026-02-01", "2026-01-31"
RATE_ID = {0: "gst-0", 0.25: "gst-0p25", 1.5: "gst-1p5", 3: "gst-3", 5: "gst-5", 12: "gst-12", 18: "gst-18", 28: "gst-28", 40: "gst-40"}
SCHEDULE_RE = re.compile(r"^\s*(?:\(\w\)\s+in the\s+)?Schedule\s+([IVX]+)\s*[–-]\s*([\d.]+)\s*%")
ROW_RE = re.compile(r"^\s*[“\"]?(\d{1,3}[A-Z]?)\.\s+(\S.*)$")
CODE_START = re.compile(r"^(\d{4}|\d{2}\b|Any\b|any\b)")


def total_rate(cgst: float) -> float:
    r = round(cgst * 2, 3)
    return int(r) if r == int(r) else r


def split_cols(rest: str) -> tuple[str, str]:
    parts = re.split(r"\s{2,}", rest.strip(), maxsplit=1)
    if len(parts) == 2 and CODE_START.match(parts[0]):
        return parts[0], parts[1]
    if CODE_START.match(rest.strip()):
        return rest.strip(), ""
    return "", rest.strip()


def codes_open(codes: str) -> bool:
    c = codes.rstrip()
    return c.endswith((",", "to", "(", "[")) or c.count("(") > c.count(")") or c.count("[") > c.count("]") or bool(re.search(r"\d{4}( \d{2})?$", c) and c.endswith(" "))


def parse_rows(text: str, schedule_hint: dict | None = None) -> list[dict]:
    """Rows as {schedule, rate, sno, codes (raw), description}."""
    rows: list[dict] = []
    last_no = None
    rate = None
    sched = None
    cur = None
    for line in text.splitlines():
        m = SCHEDULE_RE.search(line)
        if m and "%" in line and (len(line.strip()) < 80 or "in the Schedule" in line):
            sched, rate = m.group(1), total_rate(float(m.group(2)))
            cur, last_no = None, None
            continue
        if rate is None:
            continue
        m = ROW_RE.match(line)
        # A row starts with the next serial number (or a lettered insert such as 4A); a numbered list
        # inside a description does not.
        if m:
            n = int(re.match(r"\d+", m.group(1)).group())
            seq_ok = last_no is None or n == last_no + 1 or (n == last_no and not m.group(1).isdigit())
            if seq_ok and (CODE_START.match(m.group(2).strip()) or n == (last_no or 0) + 1):
                codes, desc = split_cols(m.group(2))
                cur = {"schedule": sched, "rate": rate, "sno": m.group(1), "codes": codes, "description": desc}
                rows.append(cur)
                last_no = n
                continue
        if cur is None or not line.strip():
            continue
        s = line.strip()
        lead = re.split(r"\s{2,}", s, maxsplit=1)
        if (not cur["codes"] or codes_open(cur["codes"]) or re.match(r"^\d{2}(\s\d{2})?[,)\]]?$", lead[0])) and re.match(r"^[\d(\[]", lead[0]):
            cur["codes"] += " " + lead[0]
            if len(lead) == 2:
                cur["description"] += " " + lead[1]
        else:
            cur["description"] += " " + s
    for r in rows:
        r["description"] = re.sub(r"\s+", " ", r["description"]).strip().rstrip(";”\"").strip()
        r["codes"] = re.sub(r"\s+", " ", r["codes"]).strip()
    return rows


def expand_codes(raw: str) -> tuple[list[str], str | None]:
    """'0202, 0203 to 0205, 0507 (Except 050790)' -> codes, exception note."""
    note = None
    exc = re.findall(r"[\(\[](?:Except|except|other than)[^\)\]]*[\)\]]?", raw)
    if exc:
        note = "; ".join(e.strip("()[] ") for e in exc)
        for e in exc:
            raw = raw.replace(e, " ")
    raw = re.sub(r"\bor any\b.*$", "", raw, flags=re.I)
    if re.match(r"^\s*any\b", raw, re.I):
        return [], note
    out: list[str] = []
    for part in re.split(r",|\bor\b", raw):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d{4})\s+to\s+(\d{4})$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < b - a < 60:
                out += [f"{x:04d}" for x in range(a, b + 1)]
            continue
        code = re.sub(r"\s+", "", part)
        if re.fullmatch(r"\d{2}|\d{4}|\d{6}|\d{8}", code):
            out.append(code)
    return out, note


def build(n9_text: str, n19_text: str, previous: dict | None) -> tuple[list[dict], dict]:
    rows9 = parse_rows(n9_text)
    rows19 = parse_rows(n19_text)
    stats = {"rows9": len(rows9), "rows19": len(rows19)}
    by_code: dict[str, dict] = {}

    def add(code, row, period):
        e = by_code.setdefault(code, {"hsn": code, "description": row["description"], "periods": {}, "notes": set(), "refs": set()})
        e["periods"].setdefault(period, set()).add(row["rate"])
        e["refs"].add(f"{period}:{row['schedule']}/{row['sno']}")

    for r in rows9:
        codes, note = expand_codes(r["codes"])
        for c in codes:
            add(c, r, "9/2025")
            if note:
                by_code[c]["notes"].add(note)
    vii_codes = {c for c, e in by_code.items() if any(ref.startswith("9/2025:VII/") for ref in e["refs"])}
    for r in rows19:
        codes, note = expand_codes(r["codes"])
        for c in codes:
            add(c, r, "19/2025")

    prev_rates: dict[str, set] = {}
    if previous:
        for e in previous.get("entries", []):
            m = re.search(r"gst-(\d+)(?:-(\d+))?", e.get("rateId") or "")
            if m:
                v = float(m.group(1) + ("." + m.group(2) if m.group(2) else ""))
                prev_rates.setdefault(re.sub(r"\s+", "", e["hsn"]), set()).add(int(v) if v == int(v) else v)
    # A code the 2023 schedule lists at two rates (fresh vs UHT milk) has no single earlier rate.
    prev_rate = {c: next(iter(v)) for c, v in prev_rates.items() if len(v) == 1}

    entries = []
    for code in sorted(set(by_code) | set(prev_rates)):
        e = by_code.get(code)
        hist, cond = [], None
        pre = prev_rate.get(code)
        if pre is not None and pre in RATE_ID:
            hist.append({"rateId": RATE_ID[pre], "validFrom": "2017-07-01", "validTo": GST2_TO_PREV})
        if e:
            r9 = e["periods"].get("9/2025", set())
            r19 = e["periods"].get("19/2025", set())
            if len(code) == 2:
                cond = sorted(r9 | r19)  # chapter-level rows name specific goods; never automatic
            elif len(r9) == 1:
                rate9 = next(iter(r9))
                ends = N19_TO_PREV if (code in vii_codes or r19) else None
                hist.append({"rateId": RATE_ID[rate9], "validFrom": GST2_FROM, "validTo": ends})
            elif len(r9) > 1:
                cond = sorted(r9)
            if len(r19) == 1 and len(code) > 2:
                hist.append({"rateId": RATE_ID[next(iter(r19))], "validFrom": N19_FROM, "validTo": None})
            elif code in vii_codes and not r19:
                # Schedule VII omitted with no new home for this exact code: the heading's new row
                # (prefix match) supplies the rate; this code's own history ends.
                pass
        if not hist and not cond and not (code in prev_rates):
            continue
        # fold a pre-2025 rate equal to the 9/2025 rate into one open period
        if len(hist) >= 2 and hist[0]["rateId"] == hist[1]["rateId"] and hist[1]["validFrom"] == GST2_FROM:
            hist[0] = {**hist[0], "validTo": hist[1]["validTo"]}
            del hist[1]
        out = {"hsn": code, "description": (e or {}).get("description") or next((x.get("description") for x in previous.get("entries", []) if x.get("hsn") == code), ""),
               "history": hist}
        if not cond and not e and code in prev_rates and len(prev_rates[code]) > 1:
            cond = sorted(prev_rates[code])
        if cond:
            out["conditional"] = True
            out["candidateRates"] = cond
            out["note"] = ("A chapter-level entry naming specific goods" if len(code) == 2
                           else "Listed under more than one rate (a value, use or form test)") + "; choose by the goods' description."
        if e and e["notes"]:
            out["exceptions"] = "; ".join(sorted(e["notes"]))
        if e:
            out["source"] = ", ".join(sorted(e["refs"]))
        entries.append(out)
    stats["entries"] = len(entries)
    stats["conditional"] = sum(1 for x in entries if x.get("conditional"))
    stats["withPreRate"] = len(prev_rate)
    return entries, stats


def sac_entries(prev: dict | None) -> list[dict]:
    """Services keep their 2023 rates (Notification 11/2017 as amended), in Bahi's rate ids. The
    GST 2.0 services changes (15/2025) are not parsed; GTA's is applied by hand: 12% with ITC -> 18%."""
    out = []
    for e in (prev or {}).get("sacEntries", []):
        m = re.search(r"gst-(\d+)(?:-(\d+))?", e.get("rateId") or "")
        if not m:
            continue
        v = float(m.group(1) + ("." + m.group(2) if m.group(2) else ""))
        v = int(v) if v == int(v) else v
        if v not in RATE_ID:
            continue
        code = re.sub(r"\s+", "", str(e.get("sac") or e.get("hsn") or ""))
        hist = [{"rateId": RATE_ID[v], "validFrom": "2017-07-01", "validTo": None}]
        if code.startswith("9965") and v == 12:
            hist = [{"rateId": "gst-12", "validFrom": "2017-07-01", "validTo": GST2_TO_PREV},
                    {"rateId": "gst-18", "validFrom": GST2_FROM, "validTo": None}]
        out.append({"sac": code, "description": e.get("description", ""), "history": hist,
                    "note": "Rate from the 2023 CBIC services schedule; GST 2.0 services changes (15/2025) not yet parsed."})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n9", required=True)
    ap.add_argument("--n19", required=True)
    ap.add_argument("--previous")
    ap.add_argument("--out")
    args = ap.parse_args()
    prev = json.loads(Path(args.previous).read_text()) if args.previous else None
    entries, stats = build(Path(args.n9).read_text(), Path(args.n19).read_text(), prev)
    doc = {
        "datasetVersion": N19_FROM, "schema": "hsn-common/2", "publishedOn": date.today().isoformat(),
        "description": "HSN-wise GST rates with effective-dated history: rates before GST 2.0 from the CBIC schedule (2023-04-01 revision), from 2025-09-22 per Notification 9/2025-CT(Rate), from 2026-02-01 per 19/2025-CT(Rate).",
        "source": "CBIC Notifications 9/2025 and 19/2025-Central Tax (Rate), parsed by tools/parse_rate_notification.py; earlier rates from hsn-common-20230401.json.",
        "license": "CC-BY-4.0 (government notifications are public documents)",
        "notes": "Goods only. Nil-rated goods (Notification 10/2025) are not listed after 2025-09-22. Conditional entries carry candidateRates and no automatic rate. SAC (services) rates are in sacEntries, carried from the 2023 revision with GTA updated per 15/2025.",
        "stats": stats, "entries": entries,
        "sacEntries": sac_entries(prev),
    }
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
