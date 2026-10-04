#!/usr/bin/env python3
"""
sync_upstream.py

Rebuild khata-standard datasets from the open-source ERP projects that maintain Indian tax data,
then apply this repo's hand-verified overrides on top.

    python tools/sync_upstream.py [--providers primary|fallback] [--dataset NAME ...] [--check]
                                  [--report PATH]

Each dataset lists its providers in order (see PROVIDERS below). `--providers primary` uses the
first provider of every dataset; `--providers fallback` uses the second. The GitHub workflow runs
primary first and falls back only when the primary job fails, so the two sources are independent.

Every fetch tries the source host first and then a mirror (jsDelivr for GitHub files), so a
GitHub raw outage does not fail the run.

Outputs, for each dataset whose content changed:
    data/<dataset>/<dataset>-<YYYYMMDD>.json    (YYYYMMDD = the run date)
    provenance/<run-date>-upstream-sync/source.md   (upstream URLs, commit SHAs, licences)
and a JSON report (--report) the workflow turns into the pull-request body.

Exit codes: 0 no change · 10 changes written · 1 a provider failed or a dataset failed validation.
With --check nothing is written; exit 10 means "would change".

Overrides: data/overrides/<dataset>.json holds rows checked against the official source (the Act,
a CBDT or CBIC notification). An override row replaces the upstream row with the same id and
validFrom, or adds a row upstream lacks. Overrides always win, and each carries its citation.

Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
OVERRIDES = DATA / "overrides"
UA = "khata-standard-sync/1.0 (+https://github.com/NakliTechie/khata-standard)"
ACT_2025_FROM = "2026-04-01"
ACT_1961_TO = "2026-03-31"


# --------------------------------------------------------------------------- fetching

class SourceError(Exception):
    pass


def gh_raw(repo: str, ref: str, path: str) -> list[str]:
    """The raw URL and its jsDelivr mirror for one file in a GitHub repo."""
    return [
        f"https://raw.githubusercontent.com/{repo}/{ref}/{path}",
        f"https://cdn.jsdelivr.net/gh/{repo}@{ref}/{path}",
    ]


def fetch(urls: list[str], timeout: int = 60) -> tuple[bytes, str]:
    last = None
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            if not body:
                raise SourceError(f"empty body from {url}")
            return body, url
        except (urllib.error.URLError, SourceError, TimeoutError) as e:
            last = f"{url}: {e}"
    raise SourceError(f"every mirror failed; last error {last}")


def gh_commit(repo: str, ref: str, path: str) -> str | None:
    """The latest commit touching `path`, for provenance. Best effort: the API may rate-limit."""
    url = f"https://api.github.com/repos/{repo}/commits?path={path}&sha={ref}&per_page=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        return data[0]["sha"] if data else None
    except Exception:
        return None


class Upstream:
    def __init__(self, name: str, repo: str, ref: str, license_: str):
        self.name, self.repo, self.ref, self.license = name, repo, ref, license_
        self.used: list[dict] = []

    def get(self, path: str) -> bytes:
        body, url = fetch(gh_raw(self.repo, self.ref, path))
        self.used.append({"repo": self.repo, "ref": self.ref, "path": path, "url": url,
                          "commit": gh_commit(self.repo, self.ref, path), "license": self.license})
        return body

    def json(self, path: str):
        return json.loads(self.get(path))


INDIA_COMPLIANCE = lambda: Upstream("india-compliance", "resilient-tech/india-compliance", "develop", "GPL-3.0")
ODOO = lambda: Upstream("odoo", "odoo/odoo", "master", "LGPL-3.0")
ERPNEXT_V13 = lambda: Upstream("erpnext-v13", "frappe/erpnext", "version-13", "GPL-3.0")


# --------------------------------------------------------------------------- helpers

def pct(v):
    return None if v is None else round(float(v), 4)


def clean_section(s: str) -> str:
    """'393(1) [Table: Sl. No. 6(i).D(a)] - 1023' -> '393(1) Sl. 6(i)(a)'."""
    s = re.sub(r"\s*-\s*\d{4}\s*$", "", s.strip())
    s = s.replace("[Table: Sl. No. ", "Sl. ").replace("]", "")
    s = re.sub(r"\.D\(([a-z])\)", r"(\1)", s)
    s = re.sub(r"\s+D\(([a-z])\)", r"(\1)", s)
    s = re.sub(r"Sl\.(\d)", r"Sl. \1", s)
    return re.sub(r"\s+", " ", s).strip()


def section_code(s: str) -> str | None:
    m = re.search(r"-\s*(\d{4})\s*$", s.strip())
    return m.group(1) if m else None


def merge_periods(rows: list[dict], key_fields: list[str]) -> list[dict]:
    """Sort by (id, validFrom) and fold consecutive periods whose values are equal."""
    rows = sorted(rows, key=lambda r: (r["id"], r["validFrom"]))
    out: list[dict] = []
    for r in rows:
        prev = out[-1] if out else None
        same = prev and prev["id"] == r["id"] and all(prev.get(k) == r.get(k) for k in key_fields)
        if same and (prev["validTo"] is None or prev["validTo"] >= _day_before(r["validFrom"])):
            prev["validTo"] = r["validTo"] if (r["validTo"] is None or (prev["validTo"] and r["validTo"] > prev["validTo"])) else prev["validTo"]
            continue
        out.append(dict(r))
    return out


def _day_before(iso: str) -> str:
    d = date.fromisoformat(iso)
    return date.fromordinal(d.toordinal() - 1).isoformat()


# --------------------------------------------------------------------------- TDS

def _ic_entity(e: str) -> str:
    e = e.lower()
    if e.startswith("no pan"):
        return "noPan"
    if e.startswith("individual"):
        return "individual"
    return "other"


def tds_from_india_compliance() -> tuple[list[dict], list[dict]]:
    up = INDIA_COMPLIANCE()
    new = up.json("india_compliance/income_tax_india/data/tds_details.json")
    old = up.json("india_compliance/income_tax_india/data/tds_details_old.json")
    patch = up.get("india_compliance/patches/v14/migrate_and_update_tds_section_as_per_income_tax_act_2025.py").decode()
    successor_pairs = re.findall(r'\(\s*"([^"]+)",\s*"([^"]+)"\s*\)\s*:\s*"([^"]+)"', patch)
    successors: dict[str, dict] = {}
    for old_sec, entity, new_id in successor_pairs:
        cls = _ic_entity(entity)
        if cls == "noPan":
            continue
        successors.setdefault(old_sec, {})[cls] = new_id

    def build(entries: list[dict], act: str) -> list[dict]:
        groups: dict[tuple, dict] = {}
        for e in entries:
            sec = e.get("tds_section") or ""
            # The old-Act file also carries some new-Act rows (with a 4-digit code); each Act's
            # builder keeps only its own.
            if act == "1961" and (re.fullmatch(r"\d{4}", sec) or section_code(sec) or sec.startswith(("392", "393", "394", "206C"))):
                continue  # 206C(1H) is TCS, filed here as "TDS on Sale of Goods"; it lives in tcs-sections
            code = section_code(sec) if act == "2025" else None
            ident = code or (clean_section(sec) if act == "2025" else sec)
            if not ident:
                continue
            cls = _ic_entity(e.get("entity_type", ""))
            for r in e.get("rates", []):
                k = (ident, r["from_date"])
                g = groups.setdefault(k, {
                    "id": ident, "act": act, "section": clean_section(sec) if act == "2025" else sec, "code": code,
                    "description": e.get("category_name", "").strip(),
                    "rates": {"individual": None, "other": None, "noPan": None},
                    "threshold": {"single": r.get("single_threshold") or None, "annual": r.get("cumulative_threshold") or None},
                    "validFrom": r["from_date"], "validTo": r.get("to_date"),
                })
                if g["rates"][cls] is None:
                    g["rates"][cls] = pct(r.get("tax_withholding_rate"))
        rows = list(groups.values())
        # The upstream closes every period at a financial-year end; the latest period of each
        # section stays open (new Act) or ends when the 1961 Act did.
        latest: dict[str, str] = {}
        for r in rows:
            latest[r["id"]] = max(latest.get(r["id"], ""), r["validFrom"])
        for r in rows:
            if r["validFrom"] == latest[r["id"]]:
                r["validTo"] = None if act == "2025" else ACT_1961_TO
            if act == "1961" and r["id"] in successors:
                r["successor"] = successors[r["id"]]
        return merge_periods(rows, ["rates", "threshold", "section", "code", "description", "successor"])

    rows = build(old, "1961") + build(new, "2025")
    return rows, up.used


ODOO_TAX_CSV = "addons/l10n_in/data/template/account.tax-in.csv"
ODOO_NAME = re.compile(r"^([\d.]+)% (TDS|TCS) (\d{3}\(\d\))\s*S[Il]\.\s*([0-9A-Za-z()]+)(?:\s*D\(([a-z])\))?\s*(.*?)\s*S?$")


def _odoo_rows(kind: str) -> tuple[list[tuple], list[dict]]:
    up = ODOO()
    text = up.get(ODOO_TAX_CSV).decode("utf-8")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        name = (r.get("name") or "").strip()
        m = ODOO_NAME.match(name)
        if not m or m.group(2) != kind:
            continue
        rate, _, sec, sl, sub, label = m.groups()
        section = f"{sec} Sl. {sl}" + (f"({sub})" if sub else "")
        out.append((section, float(rate), label.strip(), (r.get("description") or "").strip()))
    return out, up.used


def tds_from_odoo(current: list[dict]) -> tuple[list[dict], list[dict]]:
    """Fallback: new-Act rates from Odoo's tax templates. Odoo has no thresholds or dates, so the
    current dataset supplies them and every row it cannot place is reported, not guessed."""
    found, used = _odoo_rows("TDS")
    by_section: dict[str, set] = {}
    for section, rate, _, _ in found:
        by_section.setdefault(section, set()).add(rate)
    rows = []
    for r in current:
        if r.get("act") != "2025":
            rows.append(r)
            continue
        rates = by_section.get(r["section"])
        r2 = json.loads(json.dumps(r))
        if rates and len(rates) == 1:
            only = next(iter(rates))
            for k in ("individual", "other"):
                if r2["rates"].get(k) is not None:
                    r2["rates"][k] = only
        rows.append(r2)
    return rows, used


# --------------------------------------------------------------------------- TCS

def tcs_from_odoo(current: list[dict]) -> tuple[list[dict], list[dict]]:
    """New-Act TCS sections (394) from Odoo. Where Odoo lists two rates for one serial (an old and
    a new rate, undated), the row is left to the overrides file; the report names it."""
    found, used = _odoo_rows("TCS")
    by_section: dict[str, set] = {}
    for section, rate, label, desc in found:
        by_section.setdefault(section, set()).add(rate)
    rows = [json.loads(json.dumps(r)) for r in current]
    for r in rows:
        if r.get("act") != "2025":
            continue
        rates = by_section.get(r["section"])
        if rates and len(rates) == 1:
            r["rates"]["standard"] = next(iter(rates))
    ambiguous = sorted(s for s, v in by_section.items() if len(v) > 1)
    used.append({"note": "Odoo lists more than one rate for: " + ", ".join(ambiguous)} if ambiguous else {"note": "no ambiguous TCS rows"})
    return rows, used


def tcs_keep_current(current: list[dict]) -> tuple[list[dict], list[dict]]:
    return current, [{"note": "no second TCS source; kept the current dataset"}]


# --------------------------------------------------------------------------- GST bands

BAND_IDS = {0: "gst-0", 0.1: "gst-0p1", 0.25: "gst-0p25", 1.5: "gst-1p5", 3: "gst-3", 5: "gst-5",
            12: "gst-12", 18: "gst-18", 28: "gst-28", 40: "gst-40"}


def gst_bands_from_odoo(current: list[dict]) -> tuple[list[dict], list[dict]]:
    """Odoo's templates show which slabs exist today. A slab Odoo dropped is not ended here (Odoo
    keeps no dates); a slab Odoo has that we lack is reported so an override can date it."""
    up = ODOO()
    text = up.get(ODOO_TAX_CSV).decode("utf-8")
    seen = set()
    for r in csv.DictReader(io.StringIO(text)):
        m = re.match(r"^([\d.]+)% (?:GST|IGST) [SP]\b", (r.get("name") or "").strip())
        if m:
            seen.add(float(m.group(1)))
    have = {float(r["rate"]) for r in current}
    ov = OVERRIDES / "gst-rates.json"
    ignore = {float(x["rate"]) for x in (json.loads(ov.read_text()).get("ignoreUpstreamSlabs", []) if ov.exists() else [])}
    missing = sorted(seen - have - ignore)
    used = up.used + [{"note": "slabs in Odoo not in the dataset: " + (", ".join(map(str, missing)) or "none")}]
    if missing:
        raise SourceError(f"Odoo lists GST slabs {missing} that the dataset lacks; add them to data/overrides/gst-rates.json with their notification and date")
    return current, used


def gst_bands_from_india_compliance(current: list[dict]) -> tuple[list[dict], list[dict]]:
    up = INDIA_COMPLIANCE()
    t = up.json("india_compliance/gst_india/data/tax_defaults.json")
    seen = set()
    for templates in t.get("chart_of_accounts", {}).values():
        for it in templates.get("item_tax_templates", []):
            if it.get("gst_rate") is not None:
                seen.add(float(it["gst_rate"]))
    return current, up.used + [{"note": "india-compliance slabs: " + ", ".join(map(str, sorted(seen)))}]


# --------------------------------------------------------------------------- HSN codes

def _hsn_rows(items: list[dict]) -> list[dict]:
    rows, seen = [], set()
    for e in items:
        code = re.sub(r"\s+", "", str(e.get("hsn_code") or e.get("name") or ""))
        if not re.fullmatch(r"\d{2,8}", code) or code in seen:
            continue
        seen.add(code)
        rows.append({"hsn": code, "description": re.sub(r"\s+", " ", str(e.get("description") or "")).strip()})
    return sorted(rows, key=lambda r: r["hsn"])


def hsn_from_india_compliance(_current) -> tuple[list[dict], list[dict]]:
    up = INDIA_COMPLIANCE()
    return _hsn_rows(up.json("india_compliance/gst_india/data/hsn_codes.json")), up.used


def hsn_from_erpnext_v13(_current) -> tuple[list[dict], list[dict]]:
    up = ERPNEXT_V13()
    return _hsn_rows(up.json("erpnext/regional/india/hsn_code_data.json")), up.used


# --------------------------------------------------------------------------- datasets

PROVIDERS = {
    "tds-sections": [("india-compliance", lambda cur: tds_from_india_compliance()), ("odoo", tds_from_odoo)],
    "tcs-sections": [("odoo", tcs_from_odoo), ("current", tcs_keep_current)],
    "gst-rates": [("odoo", gst_bands_from_odoo), ("india-compliance", gst_bands_from_india_compliance)],
    "hsn-full": [("india-compliance", hsn_from_india_compliance), ("erpnext-v13", hsn_from_erpnext_v13)],
}

ENTRY_KEY = {"tds-sections": "entries", "tcs-sections": "entries", "gst-rates": "entries", "hsn-full": "entries"}


def current_dataset(name: str) -> tuple[dict | None, Path | None]:
    idx = json.loads((DATA / "index.json").read_text())
    meta = idx["datasets"].get(name) or {}
    newest = sorted((DATA / name).glob(f"{name}-*.json"))
    path = (DATA / name / meta["file"]) if meta.get("file") else (newest[-1] if newest else None)
    if newest and path and newest[-1].name > path.name:
        path = newest[-1]  # an unmerged sync is newer than the index
    if not path or not path.exists():
        return None, None
    return json.loads(path.read_text()), path


def apply_overrides(name: str, rows: list[dict]) -> tuple[list[dict], int]:
    f = OVERRIDES / f"{name}.json"
    if not f.exists():
        return rows, 0
    ov = json.loads(f.read_text())
    key = {"hsn-full": lambda r: r["hsn"], "gst-rates": lambda r: r["rateId"]}.get(name, lambda r: (r["id"], r["validFrom"]))
    by = {key(r): r for r in rows}
    drop = {tuple(d) if isinstance(d, list) else d for d in ov.get("remove", [])}
    for r in ov.get("rows", []):
        by[key(r)] = {k: v for k, v in r.items() if k != "citation"} | ({"citation": r["citation"]} if r.get("citation") else {})
    out = [r for k, r in by.items() if k not in drop and (k[0] if isinstance(k, tuple) else k) not in drop]
    sort = {"hsn-full": lambda r: r["hsn"], "gst-rates": lambda r: (r["validFrom"], r["rate"])}.get(name, lambda r: (r["id"], r["validFrom"]))
    return sorted(out, key=sort), len(ov.get("rows", []))


def validate(name: str, rows: list[dict]) -> list[str]:
    errs = []
    if not rows:
        return ["no rows"]
    if name in ("tds-sections", "tcs-sections"):
        by: dict[str, list] = {}
        for r in rows:
            for k in ("id", "act", "section", "description", "rates", "validFrom"):
                if r.get(k) in (None, ""):
                    errs.append(f"{r.get('id')}: missing {k}")
            for k, v in (r.get("rates") or {}).items():
                if v is not None and not (0 <= v <= 40):
                    errs.append(f"{r['id']} {r['validFrom']}: rate {k}={v}% outside 0-40")
            by.setdefault(r["id"], []).append(r)
        for ident, rs in by.items():
            rs = sorted(rs, key=lambda r: r["validFrom"])
            for a, b in zip(rs, rs[1:]):
                if a["validTo"] is None or a["validTo"] >= b["validFrom"]:
                    errs.append(f"{ident}: periods overlap at {b['validFrom']}")
        if not any(r["act"] == "2025" for r in rows):
            errs.append("no Income-tax Act 2025 rows")
    if name == "gst-rates":
        ids = [r["rateId"] for r in rows]
        if len(ids) != len(set(ids)):
            errs.append("duplicate rateId")
    if name == "hsn-full" and len(rows) < 10000:
        errs.append(f"only {len(rows)} HSN codes; expected the full list")
    return errs


def strip_volatile(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in ("datasetVersion", "publishedOn", "generatedAt", "provenance")}


DESCRIPTIONS = {
    "tds-sections": ("TDS sections, effective-dated: Income-tax Act 1961 sections up to 2026-03-31 and Income-tax Act 2025 "
                     "sections (392/393, with return codes) from 2026-04-01. Rates are percent; thresholds rupees."),
    "tcs-sections": "TCS sections, effective-dated: section 206C (1961 Act) to 2026-03-31, section 394 (2025 Act) from 2026-04-01.",
    "gst-rates": "GST rate bands, effective-dated, including the GST 2.0 restructuring of 2025-09-22.",
    "hsn-full": "Every HSN code with its description, as validated by the GST e-invoice portal. Codes only; rates live in hsn-common.",
}


def point_index_at(name: str, path: Path, run_day: date, provider: str, n_rows: int, n_ov: int) -> None:
    """Make data/index.json name the new file, with its hash, so the PR is publishable as-is.
    publish.yml recomputes the hash after merge; both use SHA-256 over the file bytes."""
    import hashlib
    idx_path = DATA / "index.json"
    idx = json.loads(idx_path.read_text())
    meta = idx["datasets"].setdefault(name, {})
    meta.update({
        "file": path.name, "version": run_day.isoformat(),
        "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        "status": "synced", "schema": f"{name}/2",
        "note": f"Synced {run_day.isoformat()} from {provider} (tools/sync_upstream.py): {n_rows} rows, {n_ov} hand-verified overrides.",
    })
    idx["generatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    idx_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", choices=["primary", "fallback"], default="primary")
    ap.add_argument("--dataset", action="append", choices=sorted(PROVIDERS))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--report")
    args = ap.parse_args()
    run_day = date.today()
    names = args.dataset or sorted(PROVIDERS)
    slot = 0 if args.providers == "primary" else 1
    report = {"runDate": run_day.isoformat(), "providers": args.providers, "datasets": {}}
    changed, failed = [], []

    for name in names:
        cur_doc, cur_path = current_dataset(name)
        # A dataset still in the schema-1 shape (sections / rates keyed differently) is rebuilt from
        # the overrides alone; providers then refine it.
        is_v2 = bool(cur_doc) and str(cur_doc.get("schema", "")).endswith("/2")
        cur_rows = (cur_doc or {}).get(ENTRY_KEY[name]) or [] if is_v2 else []
        provider_name, fn = PROVIDERS[name][slot]
        entry = {"provider": provider_name}
        try:
            base, _ = apply_overrides(name, cur_rows)
            rows, used = fn(base)
            rows, n_ov = apply_overrides(name, rows)
            errs = validate(name, rows)
            if errs:
                raise SourceError("; ".join(errs[:10]))
            doc = {
                "datasetVersion": run_day.isoformat(), "schema": f"{name}/2", "description": DESCRIPTIONS[name],
                "publishedOn": run_day.isoformat(),
                "source": f"Converted from {provider_name} by tools/sync_upstream.py, with {n_ov} hand-verified override rows (data/overrides/{name}.json).",
                "provenance": used, "license": "CC-BY-4.0 for this compilation; see provenance for upstream licences",
                ENTRY_KEY[name]: rows,
            }
            same = is_v2 and strip_volatile(cur_doc).get(ENTRY_KEY[name]) == rows
            entry.update({"rows": len(rows), "overrides": n_ov, "changed": not same,
                          "previous": cur_path.name if cur_path else None})
            if not same:
                changed.append(name)
                out = DATA / name / f"{name}-{run_day.strftime('%Y%m%d')}.json"
                entry["file"] = str(out.relative_to(REPO))
                if not args.check:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
                    point_index_at(name, out, run_day, provider_name, len(rows), n_ov)
            entry["upstream"] = used
        except Exception as e:  # one dataset failing must not hide the others
            entry.update({"error": f"{type(e).__name__}: {e}"})
            failed.append(name)
        report["datasets"][name] = entry
        print(f"{name}: {entry.get('error') or ('changed' if entry.get('changed') else 'no change')} via {provider_name}")

    if changed and not args.check:
        prov = REPO / "provenance" / f"{run_day.isoformat()}-upstream-sync"
        prov.mkdir(parents=True, exist_ok=True)
        lines = [f"# Upstream sync {run_day.isoformat()} ({args.providers} providers)", ""]
        for name in changed:
            e = report["datasets"][name]
            lines += [f"## {name}", f"- provider: {e['provider']}", f"- rows: {e['rows']} (overrides applied: {e['overrides']})",
                      f"- file: `{e['file']}`", "- upstream:"]
            for u in e.get("upstream", []):
                lines.append("  - " + (u.get("note") or f"{u['repo']}@{u['ref']} `{u['path']}` commit {u.get('commit') or 'unknown'} ({u['license']}) via {u['url']}"))
            lines.append("")
        (prov / "source.md").write_text("\n".join(lines))
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    if failed:
        return 1
    return 10 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
