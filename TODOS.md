# TODOS

## P1 — Before sharing with real users

### Tests (~30 tests, full coverage)
**What:** Write ~30 pytest tests covering all new features: alerts, payments, conversions, scheduler, handlers.
**Why:** No tests exist. Shipping idempotency logic, atomic DB transactions, and FIFO matching without tests means silent failures are undetectable.
**Pros:** Catches double-fire bugs, rollback failures, FIFO edge cases, handler input validation, API failure paths before a real user hits them.
**Cons:** ~30 min with CC.
**Context:** Test plan spec'd in eng review (2026-04-07). Four critical tests (from CEO review) plus full coverage:
  - `tests/test_scheduler.py` — check_alerts() (fires, no double-fire, direction='below', API failure, trend context)
  - `tests/test_database.py` — CRUD, atomic /payment rollback, FIFO /converted, P&L calculation
  - `tests/test_handlers.py` — /alert, /alerts, /payment, /converted input validation + responses
  - `tests/test_api_client.py` — get_fiat_rates_batch() + exchangerate-api.com URL verification
  Use pytest + monkeypatch. SQLite in-memory (:memory:) for DB tests. unittest.mock for Telegram + API.
**Effort:** S (human: ~1 day / CC: ~30min)
**Priority:** P1
**Depends on:** Alerts + payment feature shipped

---

### Per-User Alert Cap
**What:** Limit each user to a maximum of 10 active (untriggered) alerts at any time.
**Why:** Without a cap, a user can create unlimited alert rows. check_alerts() iterates all rows every 5 minutes, so unbounded growth degrades polling performance.
**Pros:** Protects check_alerts() loop from being a linear scan over thousands of rows.
**Cons:** Users with genuinely many alerts are capped. Limit is somewhat arbitrary.
**Context:** Not a real concern at 0-1 users. Add when check_alerts() latency becomes measurable or first user complains. Implement as: COUNT active alerts for user before INSERT; return error message if >= 10.
**Effort:** S (human: ~1h / CC: ~5min)
**Priority:** P2
**Depends on:** Alerts feature shipped, real users observed

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
