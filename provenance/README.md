# Provenance

This directory holds the evidence trail for every reference data change in the `khata-standard` repo.

## Why provenance matters

Reference data drives real tax calculations. "Trust me" is not sufficient for a free, open standard that multiple tools rely on. Every data change must be traceable back to an authoritative source — a CBIC notification, GST Council minutes, a CBDT circular, a Finance Act amendment, or similar. The provenance directory is where that traceability lives.

## Structure

Each change gets its own directory named with the pattern:

```
YYYY-MM-DD-brief-description/
```

Where `YYYY-MM-DD` is the effective date of the change (or the publication date if the change has no effective date).

Inside each directory:

- **`source.md`** — a markdown file listing the authoritative source(s), their URLs, the effective date of the change, and a brief description of what changed
- **`notification.pdf`** (or `.png`, `.html`) — an archived copy of the original document. Government websites reorganize periodically and links rot; keeping a local copy protects the evidence trail
- **`diff-summary.md`** — a human-readable summary of what changed, formatted so a non-technical reader can understand the impact

See CONTRIBUTING.md at the repo root for the full workflow and requirements.

## Current state

This directory is empty at repo bootstrap. Provenance will be added for every subsequent data change, and backfilled for existing seed data as time permits.

Historical backfill is welcome as a contribution — if you have access to the original CBIC notifications that authorized the initial seed data (GST rate bands from July 2017, the original RCM category list from Notification 13/2017, etc.), a PR that adds provenance directories for these would be genuinely useful.

## Example structure

```
provenance/
├── README.md                              (this file)
├── 2017-07-01-gst-launch/
│   ├── source.md
│   ├── notification-1-2017-central-tax-rate.pdf
│   └── diff-summary.md
└── 2025-10-01-rate-rationalization/
    ├── source.md
    ├── cbic-notification-14-2025.pdf
    ├── gst-council-55th-meeting-minutes.pdf
    └── diff-summary.md
```
