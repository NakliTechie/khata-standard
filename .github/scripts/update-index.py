#!/usr/bin/env python3
"""
update-index.py

Computes SHA-256 hashes of every dataset file referenced in data/index.json
and updates the 'sha256' field for each entry. Called by the GitHub Actions
publish workflow before deploying to the CDN.

Usage:
    python .github/scripts/update-index.py

Exit codes:
    0 — success, index.json updated
    1 — index.json not found or malformed
    2 — a referenced dataset file is missing
    3 — write failure
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
INDEX_PATH = DATA_DIR / "index.json"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 of a file and return as 'sha256:<hex>'."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def main() -> int:
    if not INDEX_PATH.exists():
        print(f"error: {INDEX_PATH} not found", file=sys.stderr)
        return 1

    try:
        with INDEX_PATH.open("r", encoding="utf-8") as f:
            index = json.load(f)
    except json.JSONDecodeError as e:
        print(f"error: index.json is malformed: {e}", file=sys.stderr)
        return 1

    if "datasets" not in index:
        print("error: index.json has no 'datasets' key", file=sys.stderr)
        return 1

    updated_count = 0
    skipped_count = 0
    errors = []

    for dataset_name, dataset_meta in index["datasets"].items():
        file_name = dataset_meta.get("file")
        if not file_name:
            skipped_count += 1
            continue

        # Dataset files normally live at data/<dataset_name>/<file>, but the
        # JSON key and the on-disk directory name are not required to match
        # (e.g. the "hsn-common" dataset lives in data/hsn/). Try the
        # conventional path first; if missing, fall back to a single-file
        # search across data/ subdirectories.
        dataset_path = DATA_DIR / dataset_name / file_name
        if not dataset_path.exists():
            matches = [p for p in DATA_DIR.glob(f"*/{file_name}") if p.is_file()]
            if len(matches) == 1:
                dataset_path = matches[0]
            elif len(matches) == 0:
                errors.append(f"missing file: {file_name} (searched data/*/)")
                continue
            else:
                errors.append(
                    f"ambiguous file: {file_name} found in multiple locations: "
                    + ", ".join(str(p) for p in matches)
                )
                continue

        try:
            new_hash = sha256_file(dataset_path)
        except OSError as e:
            errors.append(f"error reading {dataset_path}: {e}")
            continue

        old_hash = dataset_meta.get("sha256", "")
        if old_hash != new_hash:
            dataset_meta["sha256"] = new_hash
            updated_count += 1

    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 2

    # Update the generatedAt timestamp
    index["generatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        with INDEX_PATH.open("w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except OSError as e:
        print(f"error writing {INDEX_PATH}: {e}", file=sys.stderr)
        return 3

    print(f"ok: updated {updated_count} hashes, skipped {skipped_count} unpublished datasets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
