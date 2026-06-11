# Recovery IQ Sleep Engine

Recovery IQ windows are local planning estimates, not medical claims.

The sync script computes energy windows after sleep, nap, and recovery data are inserted into SQLite. Sleep Engine V2 keeps the capped/decayed debt model and uses later phase-based offsets calibrated against a RISE-like wake-time example.

Core rules:

- Base sleep need: 495 minutes.
- Next-day sleep need: base need + acute debt repay + chronic deficit repay - nap credit + recovery penalty, clamped to 450–630 minutes.
- Dynamic wake span: base 17h, moved earlier by high decayed debt, low recovery, or chronic deficit, clamped to 15h45m–17h30m.
- Grogginess: wake to wake + 60/90/120 minutes.
- Morning peak: wake + 2h45m to +5h55m.
- Afternoon dip: wake + 8h to +10h05m.
- Evening peak: wake + 12h10m to +15h02m.
- Wind-down: target bedtime - 1h34m to target bedtime.
- Estimated melatonin window: target bedtime to target bedtime + 1h.

Naps are stored in `daily_sleep.nap_minutes` and optional `daily_naps` rows. Timed naps between 10:00 and 17:00 count as partial next-day sleep need credit; aggregate-only naps also receive partial credit.

See `services/garmin-sync/sync.py`, `docs/sleep-engine-audit.md`, and `docs/sleep-engine-v2-plan.md` for implementation details and migration notes.
