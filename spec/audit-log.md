# Audit log specification

**Part of:** `.khata` format specification
**Status:** draft, will freeze at format version 1.0

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

The audit log lives in `manifest.json` under the `auditLog` key as a JSON array of entries. Implementations MAY also cache a parsed form in `books.sqlite` for fast querying, but `manifest.json` is the authoritative copy.

The log is append-only. No implementation may modify or delete existing entries.

---

## Entry format

Every entry is a JSON object with these fields:

```json
{
  "ts": "2026-04-07T14:32:11.123Z",
  "actor": "owner",
  "actorName": "Chirag",
  "origin": "https://bahi.naklitechie.com",
  "action": "invoice.create",
  "ref": "INV-2026-0001",
  "changes": { ... },
  "reason": "...",
  "hash": "sha256:a3f5..."
}
```

### Required fields

- **`ts`** — ISO 8601 UTC timestamp with millisecond precision. Example: `"2026-04-07T14:32:11.123Z"`. Implementations MUST use UTC.
- **`actor`** — one of `"owner"`, `"ca"`, or `"system"`. Identifies the category of actor that performed the action.
- **`action`** — a dotted identifier for the action type. See "Action types" below.
- **`hash`** — SHA-256 hash forming the chain. See "Hash chain" below. Format: `"sha256:"` followed by 64 lowercase hex characters.

### Optional fields

- **`actorName`** — human-readable name of the actor. For `actor: "owner"`, this is typically the company owner's name. For `actor: "ca"`, this is the CA's name as configured in the CA profile. Implementations MAY omit this, but including it is strongly recommended for forensic clarity.
- **`origin`** — the origin URL from which the change was made, e.g., `"https://bahi.naklitechie.com"`, `"file:///Users/chirag/Downloads/bahi/index.html"`, `"https://my-self-hosted-bahi.example.com"`. Required from format version 1.0 onward.
- **`ref`** — identifier of the affected entity (invoice number, customer ID, etc.). Shape depends on action type.
- **`changes`** — for edit actions, a diff showing what changed. Shape depends on action type.
- **`reason`** — free-text explanation supplied by the user. Always optional.
- Additional action-specific fields are permitted; implementations should preserve unknown fields on read and write them back unchanged.

---

## Hash chain

Each entry's `hash` field is the SHA-256 of the concatenation of:

1. The previous entry's `hash` value (or a zero hash for the first entry)
2. The canonical JSON serialization of the current entry excluding the `hash` field itself

Canonical JSON serialization for hashing:
- Keys sorted alphabetically
- No whitespace outside strings
- Unicode strings in UTF-8
- Numbers in their shortest JSON representation
- Arrays preserve order
- No trailing whitespace or newlines

The zero hash for the first entry is literally `"sha256:0000000000000000000000000000000000000000000000000000000000000000"`.

Pseudocode:

```
function computeEntryHash(entry, previousHash):
    entryCopy = copy(entry)
    delete entryCopy.hash
    canonical = canonicalJson(entryCopy)
    combined = previousHash + canonical
    return "sha256:" + hex(sha256(combined))
```

### Verification

On file open, implementations SHOULD walk the audit log from the first entry to the last and recompute each hash, verifying that the stored `hash` matches the computed value. If any mismatch is found, the file is flagged as potentially tampered. The user is shown a warning but the file can still be opened (potentially read-only depending on implementation policy).

A single mismatch anywhere in the chain invalidates all subsequent entries from a verification standpoint, because subsequent entries depend on the mismatched entry's hash.

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
- The keypair uses Ed25519 (recommended) or ECDSA P-256
- Signing is applied to the hash chain, not to individual entries
- Signature rotation (new keypair) is logged as a `keypair.rotate` action with the new public key

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

This specification is draft at format version 1.0. After Bahi's Phase 1 implementation exercises the log at scale, expected refinements include:

- Concrete guidance on `changes` field structure for each action type
- A test suite of sample files with known-good hash chains for implementations to verify against
- A dedicated viewer tool (independent of Bahi) for inspecting audit logs
- Optional post-quantum signature algorithms when practical

Implementations tracking the draft should be prepared for minor field additions and clarifications in the 1.0.x range. No breaking changes are planned between now and 1.0 freeze.
