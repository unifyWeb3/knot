# Knot threat model

## Assets

- blueprint immutability;
- participant authorization;
- workflow ordering;
- evidence integrity;
- operation idempotency;
- compensation ordering;
- terminal state and audit history.

## Threats and planned controls

### Malicious blueprint owner

The owner can choose participants and criteria but cannot rewrite a sealed blueprint. The owner/controller authorization policy must be explicit; an open-start policy would allow anyone to trigger configured participants.

### Malicious participant

A participant cannot impersonate another step because callback sender is checked against the address frozen in the definition. A participant can still withhold or misreport evidence, so public URL evidence and conservative compensation are required for material effects.

### Mutable or unrelated evidence

Every public-URL step freezes an exact evidence prefix in its sealed definition. The callback must remain inside that prefix, and the receipt records a source digest. Participant-text receipts are explicitly marked as not externally corroborated.

### Prompt injection

Treat source, context, labels, and criteria as untrusted data. Bound inputs and outputs, use structured JSON, reject malformed results, and run adversarial fixtures. A denylist alone is not a security boundary.

### Duplicate delivery and partial effects

Persist stable operation IDs. Test no effect, full effect, partial effect, lost callback, negative evidence, and repeated delivery. Define whether a retry revalidates or starts a new corrective attempt.

### Consensus and liveness

Validators independently re-derive the decision. A disagreement, unavailable source, or timeout must not advance execution. This can cause a malicious participant to force rollback; that is an explicit fail-closed trade-off.

### URL and SSRF handling

Reject malformed, non-HTTPS, local, and obviously private destinations. Do not claim complete SSRF protection unless the runtime's redirect and DNS behavior has been verified. Prefer allowlisted evidence hosts for the first release.

Implemented in `Knot._v_public_https_host`: the frozen prefix must be a directory prefix (which is what pins its authority against a participant-supplied reference) and its host must be a public, non-integer, multi-label domain. Loopback, link-local, RFC1918, carrier-grade NAT, unique-local, multicast, reserved, and documentation ranges are rejected, as are `.local`, `.internal`, `.lan`, `.intranet`, `.private`, `.home.arpa`, and bare names such as `localhost` or `metadata`. Redirects, DNS resolution, and resolver behaviour are outside the contract's control and remain unverified.

### Terminal auditability

The terminal commitment must accurately describe what it commits to. Do not claim that it includes all historical retry receipts unless those receipts are explicitly included.

## Explicit non-goals

Knot cannot make irreversible effects reversible, discover the correct compensation automatically, guarantee arbitrary external services are honest, or turn participant text into independent external proof.
