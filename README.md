# Recovery IQ

A local-only Garmin health/sleep dashboard inspired by the core ideas of RISE Sleep: sleep debt, energy windows, grogginess, productivity peaks, afternoon dip, wind-down, and estimated melatonin window.

All outputs are estimates for planning and are **not medical claims or medical advice**.

## Stack

- Frontend: React + TypeScript + Vite
- UI: Mantine UI
- Charts: Recharts
- Backend: Go + `net/http`
- Database: SQLite via `modernc.org/sqlite`
- Garmin sync: Python script using the Garmin Connect Python library (`garminconnect`, often referred to as python-garminconnect)

## Prerequisites

- Go 1.22+
- Node.js 20+
- Python 3.10+
- Make

## Setup

```bash
make setup
```

This installs Go modules, web dependencies, and a Python virtual environment for Garmin sync.

## Seed mock data / run sync

One command to create `data/health.sqlite` with 30 days of data:

```bash
make sync
```

If `GARMIN_EMAIL` and `GARMIN_PASSWORD` are not set, or Garmin login fails, this seeds realistic mock data.

## Run the API

```bash
make api
```

API runs at `http://localhost:8080`.

Endpoints:

- `GET /api/health`
- `POST /api/sync?days=14`
- `GET /api/today`
- `GET /api/sleep?days=30`
- `GET /api/recovery?days=30`
- `GET /api/energy?days=14`
- `GET /api/naps?days=30`

## Run the web app

```bash
make web
```

Web app runs at `http://localhost:5173` and proxies `/api` to the Go API.

## Run both locally

```bash
make dev
```

This seeds data, then starts the API and web app together.

## Garmin credentials

Create `services/garmin-sync/.env`:

```bash
GARMIN_EMAIL="you@example.com"
GARMIN_PASSWORD="your-password"
# Optional one-time code if you do not want an interactive prompt:
# GARMIN_MFA_CODE="123456"
```

Then run:

```bash
make sync
```

If Garmin requires MFA and you run sync in a terminal, the script prompts:

```text
Enter Garmin MFA code:
```

You can also pass a one-time code directly:

```bash
services/garmin-sync/.venv/bin/python services/garmin-sync/sync.py --days 30 --mfa-code 123456
```

After Garmin login succeeds, the sync logs each Garmin sleep/recovery fetch and explains when it falls back to mock rows. For full Python tracebacks while debugging Garmin failures:

```bash
GARMIN_DEBUG=1 services/garmin-sync/.venv/bin/python services/garmin-sync/sync.py --days 3
```

Optional environment variables:

```bash
export RECOVERYIQ_DB="/absolute/path/to/health.sqlite"
export RECOVERYIQ_ROOT="/absolute/path/to/recoveryiq"
export PORT=8080
```

## Important Garmin note

Garmin Connect access is unofficial and may break due to Garmin-side changes, MFA flows, rate limits, or library changes. Recovery IQ keeps Garmin fetching isolated in `services/garmin-sync/sync.py`; the Go API only reads SQLite or calls that script.

## Sleep/energy algorithm

Sleep Engine v2 rules:

- Base sleep need: 8h 15m.
- Dynamic next-day sleep need: base need adjusted for decayed debt, chronic deficit, nap credit, and recovery score; clamped to 7h30m–10h30m.
- Daily sleep credit: nighttime sleep + nap minutes.
- Acute debt: last 14 days of positive deficits, capped at 720 minutes.
- Decayed debt: old debt fades by 10% daily, surplus sleep pays down 50%, capped at 720 minutes. This is the primary debt display.
- Chronic deficit: average nightly shortfall over up to 90 days, not a total sum.
- Sleep consistency: bedtime and wake-time regularity over 14 days.
- Recovery score: combines decayed debt, chronic deficit, consistency, stress, resting HR vs baseline, Body Battery, and HRV status.
- Sleep pressure: low/moderate/high/very high from decayed debt + chronic deficit.
- Grogginess: wake to wake + 60/90/120 min based on debt and short last-night sleep.
- Morning peak: wake + 2h45m to wake + 5h55m.
- Afternoon dip: wake + 8h to wake + 10h05m.
- Evening peak: wake + 12h10m to wake + 15h02m.
- Target bedtime: wake + dynamic wake span, base 17h, adjusted earlier for high pressure/recovery issues and clamped to 15h45m–17h30m.
- Wind-down: target bedtime - 1h34m to target bedtime.
- Estimated melatonin window: target bedtime to target bedtime + 1h.
- Confidence: based on Garmin/mock coverage and reduced by chronic deficit or low recovery.

See `docs/sleep-engine-v2-plan.md` for the audit and implementation plan.

## Project structure

```text
apps/web/              React + Mantine UI
apps/api/              Go API
services/garmin-sync/  Python Garmin/mock sync
data/                  SQLite database location
docs/                  Notes
```
