# Sleep Engine V2 Plan

Recovery IQ sleep and energy outputs are estimates for planning only. They are not medical advice, diagnosis, or treatment.

## Existing implementation audit

### Where energy windows are calculated

- `services/garmin-sync/sync.py`
- Function: `recompute_energy(conn)`
- It runs after Garmin/mock sleep and recovery rows are written.
- It writes one row per date into `energy_windows`.

Current window logic is based on wake time (`daily_sleep.sleep_end`) plus fixed offsets:

- Grogginess: wake to wake + 60/90/120 minutes.
- Morning peak: wake + 2h30m to wake + 5h.
- Afternoon dip: wake + 7h to wake + 9h.
- Evening peak: wake + 10h30m to wake + 12h30m.
- Target bedtime: wake + 16h, adjusted earlier for sleep debt.
- Wind-down: target bedtime - 60 minutes.
- Melatonin window: target bedtime - 45 minutes to +15 minutes.

### Where sleep need is set

- `services/garmin-sync/sync.py`
- Constant: `SLEEP_NEED_MINUTES = 8 * 60 + 15` or 495 minutes.
- This constant is used as the base need for daily deficit, acute debt, decayed debt, chronic deficit, and sleep surplus.
- The frontend settings panel stores a browser-local sleep need value, but the sync/engine does not consume it yet.

### How sleep debt affects windows

Current model already distinguishes capped/decayed debt from chronic deficit:

- `compute_acute_sleep_debt(rows)`: capped 14-day sum of positive deficits.
- `compute_decayed_sleep_debt(rows)`: debt decays by 10% daily, surplus pays down 50%, capped at 720 minutes.
- `compute_chronic_deficit(rows)`: average nightly shortfall over up to 90 days.

Window effects currently use `decayed_debt`:

- If decayed debt > 180 min: grogginess becomes 90 min and bedtime moves 30 min earlier.
- If decayed debt > 300 min: grogginess becomes 120 min and bedtime moves 60 min earlier.
- If recovery score < 50: morning peak starts 30 min later, afternoon dip widens, confidence drops.
- If chronic deficit > 45 min/night: confidence is reduced.

Problem: the phase offsets are still too early. Afternoon dip, evening peak, wind-down, and melatonin are earlier than the RISE-like reference example.

### How naps are handled

Nap support exists:

- `daily_sleep.nap_minutes` stores same-day nap total.
- `daily_naps` stores optional nap detail rows (`nap_start`, `nap_end`, `duration_minutes`, `source`).
- Garmin sync extracts `dailySleepDTO.napTimeSeconds` and attempts to extract nap detail arrays when present.
- Mock data generates occasional naps.
- Sleep debt calculations count `total_sleep_minutes + nap_minutes` as daily sleep credit.
- `/api/today` exposes `naps`, and `/api/naps` exposes nap rows.

V2 needs to reuse this for dynamic next-day sleep need. If nap timing exists, only naps starting between 10:00 and 17:00 should reduce next-day sleep need. If only aggregate `nap_minutes` exists, aggregate credit is used.

### API/UI dependencies

API:

- `GET /api/today` returns `sleep`, `naps`, `recovery`, and `energy`.
- `GET /api/energy?days=N` returns `energy_windows` rows.
- `GET /api/sleep?days=N` joins selected `energy_windows` model fields onto `daily_sleep` rows.
- `GET /api/recovery?days=N` joins selected `energy_windows` model fields onto `daily_recovery` rows.

UI:

- `TodayDashboard.tsx` displays recovery score, decayed debt, acute debt, chronic deficit, consistency, nap credit, recommendations, and energy windows.
- `EnergyTimeline.tsx` charts decayed debt and chronic deficit.
- `SleepTrend.tsx` charts sleep and naps.

## Proposed V2 migration

1. Keep the existing capped/decayed/chronic debt model.
2. Replace crude phase offsets with calibrated offsets:
   - Morning peak: wake + 2h45m to +5h55m.
   - Afternoon dip: wake + 8h to +10h5m.
   - Evening peak: wake + 12h10m to +15h2m.
   - Wind-down: target bedtime - 1h34m to target bedtime.
   - Melatonin: target bedtime to target bedtime + 1h.
3. Replace fixed target bedtime with dynamic wake span:
   - Base 17h.
   - Earlier with high decayed debt, low recovery, or chronic deficit.
   - Clamp 15h45m to 17h30m.
4. Add dynamic next-day sleep need:
   - Base 495 minutes.
   - Add acute debt repay, chronic deficit repay, and recovery penalty.
   - Subtract partial nap credit.
   - Clamp 450–630 minutes.
5. Add database fields on `energy_windows`:
   - `base_sleep_need_minutes`
   - `next_day_sleep_need_minutes`
   - `sleep_need_adjustment_minutes`
   - `acute_debt_repay_minutes`
   - `chronic_deficit_repay_minutes`
   - `nap_credit_minutes`
   - `recovery_penalty_minutes`
   - `dynamic_wake_span_minutes`
6. Update API joined fields and TypeScript types.
7. Update Today UI to show dynamic sleep need and its components.
8. Add tests for calibrated wake 07:57 windows, phase offsets, dynamic need, nap credit, clamps, and no fixed final sleep need.
