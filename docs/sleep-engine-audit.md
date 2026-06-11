# Sleep Engine Audit

Date: 2026-06-11

Recovery IQ sleep and energy outputs are product heuristics for local planning. They are not medical claims, diagnosis, or treatment advice.

## Current behavior before this upgrade

### Where sleep debt is calculated

- File: `services/garmin-sync/sync.py`
- Function: `rolling_debt(conn, day_s)`
- Inputs: `daily_sleep.total_sleep_minutes` and `daily_sleep.nap_minutes`
- Current formula:
  - Select last 14 sleep rows up to `day_s`.
  - For each day: `max(0, 495 - total_sleep_minutes - nap_minutes)`.
  - Sum those positive deficits.
- The result is stored in `energy_windows.sleep_debt_minutes`.

### Where energy windows are calculated

- File: `services/garmin-sync/sync.py`
- Function: `recompute_energy(conn)`
- Current base windows:
  - Wake grogginess: wake to wake + 60/90/120 minutes depending on debt.
  - Morning peak: wake + 2.5h to wake + 5h.
  - Afternoon dip: wake + 7h to wake + 9h.
  - Evening peak: wake + 10.5h to wake + 12.5h.
  - Target bedtime: wake + 16h, moved earlier by 30/60 minutes for higher debt.
  - Wind-down: target bedtime - 60 minutes.
  - Estimated melatonin window: target bedtime - 45 minutes to +15 minutes.

### Whether sleep need is hardcoded

- `SLEEP_NEED_MINUTES = 8 * 60 + 15` in `services/garmin-sync/sync.py`.
- Settings UI has local browser values, but the sync/engine does not currently consume them.

### Whether rolling debt can grow indefinitely

- In the current 14-day query, debt cannot grow forever across all time, but it can become unrealistically large within the window and resets abruptly as old rows fall out.
- The model does not distinguish acute recent sleep loss from chronic restriction.
- Old short sleep contributes fully until it drops out of the window; there is no gradual decay.
- Surplus sleep does not reduce existing debt except by lowering that day’s deficit.

### Tables/API/UI depending on this logic

- SQLite tables:
  - `daily_sleep`: sleep timing, duration, nap minutes, score, source.
  - `daily_naps`: optional nap detail rows.
  - `daily_recovery`: Garmin/mock recovery signals.
  - `energy_windows`: stores sleep debt and calculated windows.
- API:
  - `GET /api/today` returns `sleep`, `naps`, `recovery`, and `energy`.
  - `GET /api/energy?days=N` returns `energy_windows` rows.
  - `GET /api/sleep?days=N` returns `daily_sleep` rows.
  - `GET /api/recovery?days=N` returns `daily_recovery` rows.
- UI:
  - `apps/web/src/components/TodayDashboard.tsx` displays sleep debt, confidence, energy windows, and recommendations.
  - `apps/web/src/components/EnergyTimeline.tsx` charts sleep debt.
  - `apps/web/src/components/SleepTrend.tsx` charts sleep and naps.

## Problems

1. `sleep_debt_minutes` mixes short-term and longer-term effects into one number.
2. There is no decay curve, so old sleep loss remains fully counted inside the window and disappears abruptly after it exits.
3. Chronic restriction is not represented as a baseline under-recovery state.
4. Recovery readiness does not combine sleep with Garmin recovery signals like stress, resting HR, Body Battery, and HRV status.
5. Energy windows only respond to simple sleep debt thresholds.
6. UI language can imply a single accumulating debt instead of capped/decayed estimates.

## Proposed migration

1. Keep `sleep_debt_minutes` as a backward-compatible alias for the new decayed debt.
2. Add model fields to `energy_windows`:
   - `acute_sleep_debt_minutes`
   - `chronic_sleep_deficit_minutes_per_night`
   - `decayed_sleep_debt_minutes`
   - `sleep_consistency_score`
   - `recovery_score`
   - `recovery_label`
   - `sleep_pressure_label`
   - `model_version`
3. Compute acute debt as a capped 14-day sum, capped at 720 minutes.
4. Compute decayed debt with exponential decay and partial surplus paydown, capped at 720 minutes.
5. Compute chronic deficit from average sleep credit over up to 90 days.
6. Compute sleep consistency from bedtime and wake-time variability over 14 days.
7. Compute recovery score from sleep metrics plus Garmin/mock recovery signals.
8. Adjust energy windows using decayed debt, chronic deficit, and recovery score.
9. Update API/UI to present recovery score, decayed debt, chronic deficit, consistency, and sleep pressure.
