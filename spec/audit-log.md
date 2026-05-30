# Audit log specification

**Part of:** `.khata` format specification
**Status:** draft, will freeze at format version 1.0
**Last revised:** 2026-05-30 — hash chain locked: versioned v1/v2 preimage, canonical-JSON rules, and test vectors. See [CHANGELOG](CHANGELOG.md).

---

## Purpose

The audit log is the tamper-evident record of every state-changing action performed on a `.khata` file. It provides:

1. **Forensic clarity** — who changed what, when, from where, and why
2. **Tamper evidence** — modification of the log is detectable via a hash chain
3. **Historical integrity** — reference data changes (company name edits, reference data updates) are logged so historical records can be interpreted with context
4. **Trust across actors** — when a CA receives a file, they can see exactly what the owner did since the last hand-off, and vice versa

The audit log is **not** a security mechanism in the strong cryptographic sense. A determined adversary with write access to the file can tamper; the hash chain makes casual tampering detectable but cannot prevent a replacement of the entire log. The threat model is "honest parties who want to trust what they're looking at," not "adversaries trying to forge books."

---

## Storage

The audit log lives in `books.sqlite` as an append-only `audit_log` table — one row per entry (see [`books-schema.sql`](books-schema.sql)). The manifest mirrors two anchors so the chain head can be checked without opening the database:

- `integrity.auditHead` — the latest entry's `hash` (the chain head).
- `integrity.signedBy` — the signing public key (JWK).

The log is append-only: no implementation may modify or delete existing rows, and the hash chain (below) makes any such modification detectable.

---

## Entry format

Every entry carries these fields. The reference implementation stores them as columns in an `audit_log` table; a manifest-array representation would carry the same fields as JSON object keys.

```json
{
  "ts": "2026-04-07T14:32:11.123Z",
  "actor": "owner",
  "action": "invoice.post",
  "ref": "INV-2026-0001",
  "origin": "https://bahi.naklitechie.com",
  "payload": "{\"invoiceId\":1,\"total\":118000}",
  "prev_hash": "0000…(64 hex)",
  "hash": "a3f5…(64 hex)",
  "hash_version": 2,
  "signature": "MEUCIQ…(base64, optional)"
}
```

### Required fields

- **`ts`** — ISO 8601 UTC timestamp with millisecond precision (`"2026-04-07T14:32:11.123Z"`). MUST be UTC.
- **`actor`** — one of `"owner"`, `"ca"`, `"system"`, `"ai"`. `"ai"` marks an entry drafted by an on-device or remote AI suggestion and explicitly accepted by a human; AI is never a sole actor — see "AI-assisted entries".
- **`action`** — a dotted action-type identifier. See "Action types".
- **`origin`** — the origin URL the action was taken from (`https://…`, `http://…`, `file://…`). Required from format version 1.0 onward; see "Origin tracking".
- **`payload`** — the entry body as a canonical-JSON **string** (see "Entry body"). MAY be `"{}"` for actions with no body.
- **`prev_hash`** — the previous entry's `hash`, or 64 zeros for the first entry.
- **`hash`** — the chain hash: 64 lowercase hex characters, no prefix. See "Hash chain".
- **`hash_version`** — integer hash-scheme version; `2` for new entries (absent is read as legacy v1). See "Hash versioning".

### Optional fields

- **`ref`** — identifier of the affected entity (invoice number, `customer:42`, etc.); `null`/absent when not applicable.
- **`signature`** — base64 ECDSA signature over `hash`. See "Signing". Absent when the file is unsigned.
- Additional fields are permitted; implementations MUST preserve unknown fields on read and write them back unchanged. Such fields do **not** enter the v2 hash unless they are part of the preimage field set defined under "Hash chain".

### Entry body (`payload`)

What changed — and any human-supplied context — is carried in `payload`. The reference implementation serializes the body to a canonical-JSON string and stores that string; the v2 hash embeds it verbatim. Conventional body keys include:

- **`actorName`** — human-readable actor name (owner or CA name). Strongly recommended for forensic clarity.
- **`changes`** — for edit actions, a before/after diff. Shape depends on the action type.
- **`reason`** — free-text user explanation. Always optional.
- **`aiAssisted`** — `true` when a CA in CA mode accepts an AI-drafted entry (for owner-mode AI accepts, `actor: "ai"` is used instead). Absent means `false`. See "AI-assisted entries".

Whether these live as nested keys inside `payload` or as separate top-level fields is implementation-defined, but the bytes that enter the hash are always the `payload` string of the v2 preimage.

---

## Hash chain

Each entry carries a `hash` that links it to its predecessor, making the log tamper-evident: altering any covered field of any entry — or reordering, inserting, or removing entries — breaks every hash from that point forward.

Byte-exact reference vectors for everything in this section live in **[`audit-log-test-vectors.json`](audit-log-test-vectors.json)**. An implementation that reproduces those canonical strings and hashes (including the golden chain) will verify chains written by the reference implementation.

### Hash versioning

The preimage that gets hashed is **versioned** through a `hash_version` field on the entry, so the algorithm can evolve without invalidating historical entries:

- **`hash_version: 2`** (current) — the preimage covers the chain link plus every semantic field of the entry. Conforming implementations MUST write v2 for new entries.
- **`hash_version: 1`** or absent (legacy) — an earlier scheme that hashed only the chain link, `origin`, and `payload`. Implementations MUST still *verify* such entries (older files contain them) but SHOULD NOT write new v1 entries.

A verifier selects the preimage by the entry's `hash_version`; any value other than `2` (including absence) is treated as v1.

### Canonical JSON

Reproducible hashing requires every implementation to serialize identically. The canonical form is:

- **Object keys sorted ascending by UTF-16 code unit** (JavaScript's default `Array.prototype.sort` order; lexicographic by code point across the BMP), applied recursively.
- **Primitives as `JSON.stringify` produces them**: strings double-quoted with `"`, `\`, and the C0 control characters escaped; **non-ASCII characters are NOT `\u`-escaped** (emitted directly as UTF-8); numbers in shortest round-tripping form; the literals `true`, `false`, `null`.
- **No insignificant whitespace** — nothing after `:` or `,`, no indentation, no trailing newline.
- **Array order preserved.**

Example: `{"b":1,"a":2}` → `{"a":2,"b":1}`.

### v2 preimage

For `hash_version: 2`, the preimage is the canonical JSON of this object:

```json
{ "v": 2, "prev": "<prevHash>", "ts": "<ts>", "actor": "<actor>",
  "action": "<action>", "ref": "<ref|null>", "origin": "<origin>", "payload": "<payloadString>" }
```

- `prev` — the previous entry's `hash`, or the 64-zero genesis hash for the first entry.
- `payload` — the entry body **as an already-serialized canonical-JSON string**, embedded here as a JSON string value (so its own quotes are escaped). This is how the body's bytes enter the hash regardless of how an implementation stores it physically (see "Entry body" note above).
- `ts`, `actor`, `action`, `ref`, `origin` — the entry's corresponding fields (`ref` is `null` when absent).

The hash is `sha256(canonicalJson(preimage))`, rendered as **64 lowercase hex characters, with no prefix**.

```
function computeEntryHashV2(entry, prevHash):
    preimage = canonicalJson({
        v: 2, prev: prevHash, ts: entry.ts, actor: entry.actor,
        action: entry.action, ref: entry.ref ?? null,
        origin: entry.origin, payload: entry.payload
    })
    return hex(sha256(preimage))      // 64 lowercase hex, no "sha256:" prefix
```

### v1 preimage (legacy, verify-only)

For entries whose `hash_version` is `1` or absent:

```
computeEntryHashV1(entry, prevHash) = hex(sha256(prevHash + entry.origin + entry.payload))
```

### Genesis

The `prev` of the first entry is 64 zeros: `0000000000000000000000000000000000000000000000000000000000000000`.

### Verification

On open, walk the log from first to last. For each entry: confirm its `prev` equals the running previous hash, recompute the hash using the entry's `hash_version`, and compare to the stored `hash`. A single mismatch flags the file as potentially tampered and invalidates every subsequent entry (each depends on the prior hash). The user is warned; the file MAY still open, possibly read-only depending on implementation policy.

---

## Action types

This list is the canonical set of action types as of format version 1.0. Implementations MAY log additional action types under their own reserved prefixes (e.g., `"bahi.debug.console-test"`) but SHOULD NOT reuse the canonical prefixes for non-standard purposes.

### Transaction actions

- `invoice.create` / `invoice.edit-draft` / `invoice.post` / `invoice.reverse`
- `purchase.create` / `purchase.edit-draft` / `purchase.post` / `purchase.reverse`
- `receipt.create` / `receipt.post`
- `payment.create` / `payment.post`
- `credit-note.create` / `credit-note.post`
- `debit-note.create` / `debit-note.post`
- `journal-voucher.create` / `journal-voucher.post`
- `contra.create` / `contra.post`
- `delivery-challan.create` / `delivery-challan.post`
- `advance-receipt.create` / `advance-receipt.post` / `advance-receipt.adjust`
- `refund-voucher.create` / `refund-voucher.post`

### Master actions

- `customer.create` / `customer.edit` / `customer.archive`
- `vendor.create` / `vendor.edit` / `vendor.archive`
- `item.create` / `item.edit` / `item.archive`
- `account.create` / `account.edit` / `account.archive`
- `bank-account.create` / `bank-account.edit` / `bank-account.close`

### Company and settings actions

- `company.create` — initial file creation
- `company.edit` — company profile edit (name, address, logo, etc.); `changes` field carries the diff
- `settings.edit` — non-identity settings change
- `uitier.change` — progressive unlock tier changed
- `composition-scheme.enable` / `composition-scheme.disable`

### Reference data actions

- `reference.update` — user refreshed a reference dataset from CDN; `changes` field includes dataset name, from-version, to-version

### Compliance actions

- `return.filed` — user marked a GST return (GSTR-1, GSTR-3B, CMP-08, GSTR-4) as filed; triggers period lock
- `return.unfiled` — user unmarked a return as filed; removes period lock
- `fy.close` — financial year closed via year-end rollover wizard
- `fy.reopen` — closed FY reopened (destructive, heavily gated)

### File lifecycle actions

- `file.open` — session-start marker; includes origin and mode (owner/ca)
- `file.close` — session-end marker
- `file.snapshot` — explicit snapshot taken (versus automatic rolling snapshots, which are not logged)
- `file.backup-now` — "Backup Now" button clicked, dated archive exported
- `file.import-tally` — Tally XML import performed
- `file.import-khata` — another `.khata` file imported (divergence reconciliation)
- `keypair.rotate` — audit log signing keypair rotated (new origin, browser data clear, or user-initiated)

### CA mode actions

- `ca.mode-enter` — switched to CA mode
- `ca.mode-exit` — switched back to owner mode
- `ca.annotation.add` / `ca.annotation.edit` / `ca.annotation.delete`
- `ca.entry.mark-reviewed` / `ca.entry.unmark-reviewed`
- `ca.review-report.generate`

---

## Signing

In addition to the hash chain, entries MAY be signed by a keypair generated at first launch and stored in the implementation's local browser storage (for Bahi, this is IndexedDB). The public key of the current keypair is stored in the manifest under `integrity.signedBy`.

Signing is OPTIONAL at format version 1.0. A file without signatures is still valid. Signing provides a weaker-than-cryptographic but useful additional tamper-evidence layer: if an attacker copies the file and modifies it without access to the original signing key, the signatures will no longer verify.

When signing is used:
- Each entry's `hash` is signed and the base64 signature stored in that entry's `signature` field; because each `hash` transitively covers the whole chain, signing per entry also pins the chain.
- The reference implementation uses **ECDSA P-256** with SHA-256, exporting the public key as a JWK in `manifest.integrity.signedBy`. Ed25519 is also permitted; the algorithm is identified by the JWK.
- A signature that fails to verify means the entry was written by a different keypair (e.g. the file was edited on another machine) **or** was tampered. This is surfaced as a distinct signal from a hash-chain break — it is not folded into chain validity, so a legitimately multi-keypair file does not false-alarm.
- Signature rotation (new keypair) is logged as a `keypair.rotate` action carrying the new public key.

---

## AI-assisted entries

Format version 1.0 recognises that some implementations may surface AI-drafted entry forms (e.g., extracting line items from an uploaded vendor bill, or composing a voucher from natural-language input). The format takes a position on how these entries are recorded:

1. **AI is never an actor on its own.** A human always accepts an AI-drafted entry before it is posted; the audit log records the human acceptance, not the AI proposal.
2. **`actor: "ai"`** is used when an owner-mode user accepts an AI-drafted entry. The AI is the proximate cause of the entry's contents; the owner is the consenting party.
3. **`actor: "ca"` + `aiAssisted: true`** is used when a CA in CA-mode accepts an AI-drafted entry. The CA remains the accountable actor; the boolean flag preserves the AI-assist provenance.
4. **AI prompts are not logged.** Only the accepted entry is logged. The natural-language prompt, the extracted OCR text, and any rejected drafts MUST NOT appear in the audit log payload — they often contain sensitive financial context and add no forensic value beyond the accepted entry.
5. **No AI-specific fields beyond `aiAssisted`.** Implementations MUST NOT add fields like `aiProvider`, `aiModel`, `aiConfidence`, etc. to the audit-log payload at format version 1.0. These are useful for debugging in implementation memory but are not part of the format's forensic surface.

The hash chain treats the new actor value and the optional `aiAssisted` field exactly like any other actor or payload field — they participate in canonical-JSON serialization and signing without special-casing.

---

## Origin tracking

The `origin` field on every entry records the URL from which the action was taken. This matters when a single `.khata` file is opened from multiple origins — e.g., `https://bahi.naklitechie.com` during most of its life, and then from a locally-saved `file://` copy of Bahi for a brief period.

Cross-origin tracking is a first-class concern because:
- Browser storage (workspace, signing keypair, CA profile) is per-origin and doesn't carry across
- Concurrent edits from different origins are possible since cross-origin tabs can't share a `BroadcastChannel` lock
- CAs reviewing a file need to see if it was edited from a locally-saved copy

Valid origin values include any URL scheme: `https://`, `http://`, `file://`. Implementations MUST stamp `origin` on every entry from format version 1.0 onward.

---

## Implementer notes

- The hash chain creates a strict ordering. Concurrent entries from different sessions (possible in some edge cases) must be serialized before writing. The `ts` field should be used as a tie-breaker for entries with identical timestamps, falling back to lexicographic comparison of action types and refs.
- When implementing the canonical JSON serialization, be careful about numeric precision. JavaScript's `JSON.stringify` is not canonical (object key order varies). Use a canonicalizing serializer like [json-canonicalize](https://github.com/erdtman/canonicalize) or equivalent.
- The audit log grows without bound. For typical SMB use over a few years, expect a few thousand entries. For heavy use, tens of thousands. This is manageable as JSON but implementations should not load the entire log on every operation; a cursor-based or incremental approach is better.
- When displaying the audit log to users, group related entries (e.g., an invoice create + its posting) to avoid overwhelming detail. The full raw log should be accessible on demand for forensic review.

---

## Status and future work

This specification is draft at format version 1.0, now exercised by the reference implementation (Bahi) at scale — thousands of entries across multi-year sample files. The hash chain — canonical-JSON rules, the versioned (v1/v2) preimage, the hash format, and signing — is **locked** and backed by [`audit-log-test-vectors.json`](audit-log-test-vectors.json).

Remaining before the 1.0 freeze:

- Concrete, per-action-type guidance on `payload` / `changes` body structure. (The envelope and the hash are locked; the per-action body shapes are still informed by implementation.)
- A dedicated viewer tool (independent of Bahi) for inspecting audit logs.
- Optional post-quantum signature algorithms when practical.

Implementations tracking the draft should expect minor body-shape clarifications in the 1.0.x range. No breaking changes to the hash chain are planned between now and the 1.0 freeze.
