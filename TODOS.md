# TODOS

## P1 — Before sharing with real users

### Tests (4 critical)
**What:** Write 4 pytest tests for the alert and payment features.
**Why:** No tests exist. Shipping idempotency logic and atomic DB transactions without tests means silent failures are undetectable.
**Pros:** Catches double-fire bugs, rollback failures, FIFO edge cases before a real user hits them.
**Cons:** ~15 min with CC.
**Context:** The 4 tests are already spec'd in the CEO review:
  1. `test_alert_fires_when_rate_above_target` — mock API, insert alert, run check_alerts(), assert was_triggered=1
  2. `test_alert_does_not_double_fire` — insert alert with was_triggered=1, run job, assert send_message NOT called
  3. `test_payment_and_alert_created_atomically` — simulate DB error on alert insert, assert payments table also empty
  4. `test_converted_fifo_picks_oldest_payment` — insert 2 pending USD payments, /converted, assert oldest marked
**Effort:** S (human: ~1 day / CC: ~15min)
**Priority:** P1
**Depends on:** Alerts + payment feature shipped

---

## P2 — v1.1 (after first real users)

### Weekly Brief (Digest)
**What:** Every Monday at 9am UTC (12pm Moscow), send users: last week's best rate, this week's range so far, pending payment reminder.
**Why:** Re-engagement. Users who stop checking the bot still get value delivered. The difference between a tool you use and a service you're subscribed to.
**Pros:** Drives retention, surfaces the rate_history data already being collected.
**Cons:** Requires user_prefs table, digest scheduler job, user opt-in/out flow.
**Context:** rate_history table is already being built in v1. Weekly brief is the primary consumer of that data. Deferred because /alerts covers the manual check-in use case, and user count is 0 — no point building retention before there's anyone to retain.
**Effort:** M (human: ~1 day / CC: ~20min)
**Priority:** P2
**Depends on:** v1 shipped, at least 1 real user

### exchangerate-api.com Fallback
**What:** Add exchangerate-api.com as a fallback when open.er-api.com fails.
**Why:** open.er-api.com has no documented SLA. If it goes down, all fiat alerts silently fail.
**Pros:** Resilience, no single point of failure.
**Cons:** Another API key/URL to manage.
**Context:** v1 switches to exchangerate-api.com as primary (10k req/month free, adequate). This TODO is about adding the original as a fallback, not replacing it.
**Effort:** S (human: ~2h / CC: ~10min)
**Priority:** P2
**Depends on:** v1 shipped

---

## P3 — After real conversion data exists

### /compare command
**What:** `/compare USD EUR` — "If you'd held EUR instead of USD last month, +₽800 per $1k."
**Why:** Some freelancers can choose their invoice currency. This tells them which to request.
**Pros:** High perceived value, differentiates from generic price bots.
**Cons:** Needs real conversion history. Without data, the comparison is meaningless.
**Context:** The conversions table is already being built in v1. This command is the natural consumer after 2-3 months of real data. Don't build it until you have at least 10 real conversions logged.
**Effort:** S (human: ~4h / CC: ~10min)
**Priority:** P3
**Depends on:** conversions table with ≥10 real entries

### InlineKeyboard One-Tap Re-Alert
**What:** When an alert fires, include an inline button "🔁 Set same alert again" that re-creates the alert without the user having to type the command.
**Why:** Current one-shot UX requires typing `/alert USD 95` again. Friction.
**Pros:** Better UX for repeat alerters.
**Cons:** InlineKeyboard requires callback handler, more code.
**Context:** One-shot is correct for the payment conversion use case. This is polish, not core.
**Effort:** S (human: ~4h / CC: ~10min)
**Priority:** P3
**Depends on:** v1 shipped, user feedback confirming the friction is real
