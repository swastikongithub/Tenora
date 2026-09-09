# Claude Code Implementation Specification — Fix: Real Billing Period Dates

**Scope:** close the gap D3 explicitly flagged - the CHARGED event
handler currently synthesizes a local billing period
(default_period(plan, start=current_period_end)) instead of using the
real period dates Razorpay actually sends. This is a small, scoped fix,
not a redesign.

**Not in scope:** D4, D5-D8, any other change to the adapter interface,
any change to ACTIVATED/CANCELLED/PAYMENT_TROUBLE handling beyond what's
needed to plumb real dates through where they're available.

---

## 1. Objective

A billing engine that doesn't use the real billing period a payment
provider reports is a real correctness gap - D3's own report named this
honestly rather than hiding it, and it's worth closing before D4 builds
ordering/timing logic on top of dates that are currently only
approximate.

This is a deliberate, justified extension of NormalizedEvent, not a
violation of "don't modify the adapter interface." That rule (from D3's
spec) was about not touching the interface casually or speculatively;
this is a targeted addition of two fields to close a named, real gap.
State this reasoning in the code/commit, so it doesn't read as an
inconsistency with the prior rule.

Same design principle as the correlation-ID decision, applied here too:
the real period dates must be stored on the WebhookEvent row itself at
write time (not just left inside raw_payload), so the retry/backfill
management command - which has no live adapter context - never needs
provider-specific knowledge to get correct data. Re-parsing raw payloads
at processing time was already rejected once for this exact reason; the
same reasoning applies to period dates.

## 2. Inspect Before Implementing

```
apps/billing/gateway/base.py            - NormalizedEvent - confirm
                                           exact current fields
apps/billing/gateway/razorpay.py        - parse_webhook_event - confirm
                                           the payload path to
                                           current_start/current_end
                                           (D3's own report already
                                           confirmed
                                           payload.subscription.entity
                                           carries these as Unix
                                           timestamps - verify still
                                           true, don't re-assume)
apps/billing/gateway/mock.py            - MockGatewayAdapter's
                                           equivalent construction
apps/billing/models.py                  - WebhookEvent, Subscription -
                                           current fields
apps/billing/services.py                - WebhookProcessingService's
                                           CHARGED handler, default_period,
                                           record_event
config/settings.py                      - confirm USE_TZ / timezone
                                           handling convention before
                                           converting Unix timestamps -
                                           don't assume naive vs.
                                           timezone-aware
```

## 3. Existing Functionality That Must Not Change

- D3's idempotency guarantees, the inline-processing-never-affects-200
  rule, every other EventType handler - untouched.
- All 202 existing backend tests must still pass.

## 4. Required Changes

### 4.1 NormalizedEvent gains two optional fields

period_start: datetime | None
period_end: datetime | None

Optional because not every event type carries period data.

### 4.2 RazorpayGatewayAdapter.parse_webhook_event

Extract current_start/current_end from the payload (verify the exact
path per section 2), convert the Unix timestamps to timezone-aware
datetime objects consistent with this project's actual timezone
convention (don't assume - check USE_TZ and how other datetime fields
in this codebase are handled). If the fields are absent from a given
payload, None - don't crash, don't fabricate a fallback value at this
layer (that decision belongs in the handler, section 4.5).

### 4.3 MockGatewayAdapter

Gains the ability to include period dates in its synthetic events, so
tests can exercise both the "real dates present" and "real dates absent"
paths deliberately.

### 4.4 WebhookEvent gains period_start/period_end

Nullable DateTimeFields. Populated from NormalizedEvent at the same
point external_subscription_id was just wired in (the correlation fix)
- same write-time-normalization principle, applied consistently.

### 4.5 CHARGED handler — use real dates when present, fall back honestly when absent

If the WebhookEvent row has real period_start/period_end, use them
directly to set the Subscription's period fields - no local
calculation. If they're genuinely absent (a payload that legitimately
lacked them, or a MockGatewayAdapter test scenario configured without
them), fall back to the existing default_period() calculation with a
logged warning noting real dates weren't available - this keeps the
fallback as a safety net for a genuine edge case, while making it
visible/auditable rather than silently indistinguishable from the real
case.

## 5. Files Likely Affected

```
new:      apps/billing/migrations/... (WebhookEvent.period_start/period_end)
modified: apps/billing/gateway/base.py
          apps/billing/gateway/razorpay.py
          apps/billing/gateway/mock.py
          apps/billing/models.py
          apps/billing/services.py (record_event, the CHARGED handler)
          apps/billing/views.py (if record_event's call site needs updating)
          tests for all of the above
```

## 6. Business Rules

- Real provider-supplied period dates are always preferred over any
  locally synthesized value.
- The fallback path is logged, never silent.

## 7. Security Requirements

No change - this is domain-data correctness, not a new external surface.

## 8. Edge Cases

- A CHARGED event with real dates, processed twice (idempotency,
  carried over from D3) - must not double-apply or drift.
- A CHARGED event genuinely missing period data (some legitimate
  provider payload variant, or a test simulating this) - falls back
  correctly, logs the fallback, does not crash.
- Unix-timestamp-to-datetime conversion - verify against the project's
  actual timezone convention, not assumed.

## 9. Tests Required

- parse_webhook_event correctly extracts and converts real period
  dates from a verified Razorpay payload shape into timezone-aware
  datetime objects.
- MockGatewayAdapter can produce events with and without period dates.
- CHARGED handler: given real dates, the Subscription's period fields
  are set to those exact values (not the locally-computed fallback) -
  this is the core proof.
- CHARGED handler: given absent dates, falls back to default_period()
  and logs a warning.
- Idempotency still holds with real dates present (reprocessing doesn't
  double-shift).

## 10. Acceptance Criteria

1. manage.py test - full count reported (baseline 202).
2. manage.py check, makemigrations --check - clean.
3. Report: the exact timezone-conversion approach used and why, and
   confirmation both the "real dates present" and "real dates absent"
   paths are tested.
4. git status - no unrelated file changed.

## 11. Must NOT Do

- Do not change any other EventType handler beyond what's needed to
  plumb period dates through.
- Do not silently drop the fallback path - a payload genuinely lacking
  period data must still be handled without crashing.
- Do not build D4 or any later stage.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code - small
scope, but touches billing-correctness logic, so still worth a plan
review before implementation.

---

## Ready-to-paste prompt for Claude Code

Read docs/fix-real-period-dates-spec.md, then inspect the repository.
Produce an implementation plan and wait for my approval before writing any code.
