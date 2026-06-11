#!/usr/bin/env python3
"""Garmin/Mock sync for Recovery IQ.

This script is intentionally isolated from the Go API because Garmin Connect
access is unofficial and best handled through python-garminconnect. If Garmin
credentials are missing or any login/fetch step fails, the script falls back to
realistic mock data so the local app remains usable.
"""
from __future__ import annotations

import argparse
import os
import random
import sqlite3
import statistics
import sys
import traceback
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

SLEEP_NEED_MINUTES = 8 * 60 + 15
DEBT_CAP_MINUTES = 720
MODEL_VERSION = "sleep-engine-v2"
DEFAULT_WAKE_TIME = time(7, 0)

SYNC_DIR = Path(__file__).resolve().parent
ROOT = SYNC_DIR.parents[1]
DOTENV_PATH = SYNC_DIR / ".env"
DB_PATH = Path(os.environ.get("RECOVERYIQ_DB", ROOT / "data" / "health.sqlite"))


def load_dotenv(path: Path = DOTENV_PATH) -> Dict[str, str]:
    """Load key/value pairs from services/garmin-sync/.env.

    Kept dependency-free so mock sync still works even before Python packages are
    installed. Supports simple KEY=value lines, optional `export`, quotes, and
    comments.
    """
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def iso_minute(dt: datetime) -> str:
    return dt.replace(second=0, microsecond=0).isoformat(timespec="minutes")


def parse_dt(value: Any) -> Optional[datetime]:
    """Parse Garmin timestamps.

    Garmin sleep payloads may contain ISO strings, Unix seconds, or Unix
    milliseconds. The sleep fields seen from Garmin Connect commonly arrive as
    millisecond integers, e.g. 1780999460000.
    """
    if value is None or value == "":
        return None

    try:
        if isinstance(value, (int, float)):
            timestamp = float(value)
            # Treat large Unix values as milliseconds, smaller values as seconds.
            if timestamp > 10_000_000_000:
                timestamp = timestamp / 1000.0
            # Garmin's *Local timestamp* numeric fields are already shifted to
            # the user's local wall-clock time. Use UTC conversion to avoid
            # applying the computer timezone a second time.
            return datetime.utcfromtimestamp(timestamp).replace(tzinfo=None)

        text = str(value).strip()
        if not text:
            return None
        if text.isdigit():
            timestamp = float(text)
            if timestamp > 10_000_000_000:
                timestamp = timestamp / 1000.0
            return datetime.utcfromtimestamp(timestamp).replace(tzinfo=None)

        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def to_minutes(seconds: Any) -> Optional[int]:
    if seconds is None:
        return None
    try:
        return int(round(float(seconds) / 60.0))
    except Exception:
        return None


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS daily_sleep (
            date TEXT PRIMARY KEY,
            sleep_start TEXT,
            sleep_end TEXT,
            total_sleep_minutes INTEGER,
            deep_minutes INTEGER,
            light_minutes INTEGER,
            rem_minutes INTEGER,
            awake_minutes INTEGER,
            nap_minutes INTEGER DEFAULT 0,
            sleep_score INTEGER,
            source TEXT
        );

        CREATE TABLE IF NOT EXISTS daily_naps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            nap_start TEXT,
            nap_end TEXT,
            duration_minutes INTEGER NOT NULL,
            source TEXT,
            UNIQUE(date, nap_start, nap_end, duration_minutes, source)
        );

        CREATE TABLE IF NOT EXISTS daily_recovery (
            date TEXT PRIMARY KEY,
            resting_hr INTEGER,
            hrv_status TEXT,
            stress_avg INTEGER,
            body_battery_start INTEGER,
            body_battery_end INTEGER,
            respiration_avg REAL,
            spo2_avg REAL,
            source TEXT
        );

        CREATE TABLE IF NOT EXISTS energy_windows (
            date TEXT PRIMARY KEY,
            wake_time TEXT,
            grogginess_start TEXT,
            grogginess_end TEXT,
            morning_peak_start TEXT,
            morning_peak_end TEXT,
            afternoon_dip_start TEXT,
            afternoon_dip_end TEXT,
            evening_peak_start TEXT,
            evening_peak_end TEXT,
            wind_down_start TEXT,
            target_bedtime TEXT,
            melatonin_window_start TEXT,
            melatonin_window_end TEXT,
            sleep_debt_minutes INTEGER,
            acute_sleep_debt_minutes INTEGER DEFAULT 0,
            chronic_sleep_deficit_minutes_per_night INTEGER DEFAULT 0,
            chronic_deficit_label TEXT DEFAULT 'none',
            decayed_sleep_debt_minutes INTEGER DEFAULT 0,
            sleep_consistency_score INTEGER DEFAULT 100,
            recovery_score INTEGER DEFAULT 100,
            recovery_label TEXT DEFAULT 'excellent',
            sleep_pressure_label TEXT DEFAULT 'low',
            model_version TEXT DEFAULT 'sleep-engine-v2',
            calculation_explanation TEXT,
            base_sleep_need_minutes INTEGER DEFAULT 495,
            next_day_sleep_need_minutes INTEGER DEFAULT 495,
            sleep_need_adjustment_minutes INTEGER DEFAULT 0,
            acute_debt_repay_minutes INTEGER DEFAULT 0,
            chronic_deficit_repay_minutes INTEGER DEFAULT 0,
            nap_credit_minutes INTEGER DEFAULT 0,
            recovery_penalty_minutes INTEGER DEFAULT 0,
            dynamic_wake_span_minutes INTEGER DEFAULT 1020,
            confidence TEXT
        );
        """
    )
    # Lightweight migrations for databases created by earlier MVP versions.
    sleep_columns = {row[1] for row in conn.execute("PRAGMA table_info(daily_sleep)").fetchall()}
    if "nap_minutes" not in sleep_columns:
        conn.execute("ALTER TABLE daily_sleep ADD COLUMN nap_minutes INTEGER DEFAULT 0")

    energy_columns = {row[1] for row in conn.execute("PRAGMA table_info(energy_windows)").fetchall()}
    energy_additions = {
        "acute_sleep_debt_minutes": "INTEGER DEFAULT 0",
        "chronic_sleep_deficit_minutes_per_night": "INTEGER DEFAULT 0",
        "chronic_deficit_label": "TEXT DEFAULT 'none'",
        "decayed_sleep_debt_minutes": "INTEGER DEFAULT 0",
        "sleep_consistency_score": "INTEGER DEFAULT 100",
        "recovery_score": "INTEGER DEFAULT 100",
        "recovery_label": "TEXT DEFAULT 'excellent'",
        "sleep_pressure_label": "TEXT DEFAULT 'low'",
        "model_version": "TEXT DEFAULT 'sleep-engine-v2'",
        "calculation_explanation": "TEXT",
        "base_sleep_need_minutes": "INTEGER DEFAULT 495",
        "next_day_sleep_need_minutes": "INTEGER DEFAULT 495",
        "sleep_need_adjustment_minutes": "INTEGER DEFAULT 0",
        "acute_debt_repay_minutes": "INTEGER DEFAULT 0",
        "chronic_deficit_repay_minutes": "INTEGER DEFAULT 0",
        "nap_credit_minutes": "INTEGER DEFAULT 0",
        "recovery_penalty_minutes": "INTEGER DEFAULT 0",
        "dynamic_wake_span_minutes": "INTEGER DEFAULT 1020",
    }
    for column, ddl in energy_additions.items():
        if column not in energy_columns:
            conn.execute(f"ALTER TABLE energy_windows ADD COLUMN {column} {ddl}")
    conn.commit()


def upsert_sleep(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO daily_sleep (
            date, sleep_start, sleep_end, total_sleep_minutes, deep_minutes,
            light_minutes, rem_minutes, awake_minutes, nap_minutes, sleep_score, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            sleep_start=excluded.sleep_start,
            sleep_end=excluded.sleep_end,
            total_sleep_minutes=excluded.total_sleep_minutes,
            deep_minutes=excluded.deep_minutes,
            light_minutes=excluded.light_minutes,
            rem_minutes=excluded.rem_minutes,
            awake_minutes=excluded.awake_minutes,
            nap_minutes=excluded.nap_minutes,
            sleep_score=excluded.sleep_score,
            source=excluded.source
        """,
        (
            row["date"], row["sleep_start"], row["sleep_end"], row["total_sleep_minutes"],
            row["deep_minutes"], row["light_minutes"], row["rem_minutes"], row["awake_minutes"],
            row.get("nap_minutes", 0), row["sleep_score"], row["source"],
        ),
    )


def upsert_recovery(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO daily_recovery (
            date, resting_hr, hrv_status, stress_avg, body_battery_start,
            body_battery_end, respiration_avg, spo2_avg, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            resting_hr=excluded.resting_hr,
            hrv_status=excluded.hrv_status,
            stress_avg=excluded.stress_avg,
            body_battery_start=excluded.body_battery_start,
            body_battery_end=excluded.body_battery_end,
            respiration_avg=excluded.respiration_avg,
            spo2_avg=excluded.spo2_avg,
            source=excluded.source
        """,
        (
            row["date"], row["resting_hr"], row["hrv_status"], row["stress_avg"],
            row["body_battery_start"], row["body_battery_end"], row["respiration_avg"],
            row["spo2_avg"], row["source"],
        ),
    )


def replace_naps(conn: sqlite3.Connection, day_s: str, naps: list[Dict[str, Any]]) -> None:
    conn.execute("DELETE FROM daily_naps WHERE date = ?", (day_s,))
    for nap in naps:
        if int(nap.get("duration_minutes") or 0) <= 0:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO daily_naps (date, nap_start, nap_end, duration_minutes, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                day_s,
                nap.get("nap_start"),
                nap.get("nap_end"),
                int(nap.get("duration_minutes") or 0),
                nap.get("source", "unknown"),
            ),
        )


def mock_day(day: date) -> tuple[Dict[str, Any], Dict[str, Any], list[Dict[str, Any]]]:
    """Generate deterministic, realistic-enough local data for one day."""
    rng = random.Random(day.toordinal())

    sleep_total = int(max(330, min(560, rng.gauss(455, 50))))
    wake_minutes = int(max(330, min(510, rng.gauss(420, 35))))
    wake = datetime.combine(day, time(0, 0)) + timedelta(minutes=wake_minutes)
    sleep_start = wake - timedelta(minutes=sleep_total + rng.randint(10, 45))

    deep = int(sleep_total * rng.uniform(0.14, 0.22))
    rem = int(sleep_total * rng.uniform(0.18, 0.25))
    awake = rng.randint(8, 35)
    light = max(0, sleep_total - deep - rem)
    score = int(max(45, min(96, 55 + (sleep_total - 360) * 0.10 + deep * 0.05 - awake * 0.2 + rng.randint(-7, 7))))

    stress = int(max(18, min(82, rng.gauss(38, 13))))
    resting_hr = int(max(45, min(78, rng.gauss(58, 6) + (stress - 40) * 0.05)))
    bb_start = int(max(35, min(100, 45 + (sleep_total - 360) * 0.12 + rng.randint(-8, 12))))
    bb_end = int(max(5, min(80, bb_start - rng.randint(25, 55) + (40 - stress) * 0.2)))
    hrv = rng.choices(["balanced", "unbalanced", "low", "unknown"], weights=[62, 20, 12, 6])[0]

    naps: list[Dict[str, Any]] = []
    nap_minutes = 0
    if rng.random() < 0.28:
        nap_minutes = rng.choice([15, 20, 25, 30, 35, 40, 45])
        nap_start = datetime.combine(day, time(13, 0)) + timedelta(minutes=rng.randint(0, 180))
        nap_end = nap_start + timedelta(minutes=nap_minutes)
        naps.append({
            "date": day.isoformat(),
            "nap_start": iso_minute(nap_start),
            "nap_end": iso_minute(nap_end),
            "duration_minutes": nap_minutes,
            "source": "mock",
        })

    sleep = {
        "date": day.isoformat(),
        "sleep_start": iso_minute(sleep_start),
        "sleep_end": iso_minute(wake),
        "total_sleep_minutes": sleep_total,
        "deep_minutes": deep,
        "light_minutes": light,
        "rem_minutes": rem,
        "awake_minutes": awake,
        "nap_minutes": nap_minutes,
        "sleep_score": score,
        "source": "mock",
    }
    recovery = {
        "date": day.isoformat(),
        "resting_hr": resting_hr,
        "hrv_status": hrv,
        "stress_avg": stress,
        "body_battery_start": bb_start,
        "body_battery_end": bb_end,
        "respiration_avg": round(rng.uniform(12.0, 16.5), 1),
        "spo2_avg": round(rng.uniform(94.0, 99.0), 1),
        "source": "mock",
    }
    return sleep, recovery, naps


def dig(obj: Any, *keys: str) -> Any:
    current = obj
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def extract_sleep(day: date, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    daily = payload.get("dailySleepDTO") or payload.get("dailySleepDto") or payload
    start = parse_dt(daily.get("sleepStartTimestampLocal") or daily.get("sleepStartTimestampGMT"))
    end = parse_dt(daily.get("sleepEndTimestampLocal") or daily.get("sleepEndTimestampGMT"))
    total = to_minutes(daily.get("sleepTimeSeconds") or daily.get("totalSleepTimeSeconds"))
    nap_minutes = to_minutes(daily.get("napTimeSeconds")) or 0
    if not total and start and end:
        total = int((end - start).total_seconds() / 60)
    if not total or not end:
        return None

    # If Garmin sends an implausible local timestamp (for example a timezone
    # field interpreted incorrectly), keep the duration but anchor the sleep to
    # the calendar day wake time so downstream energy windows remain sane.
    if start and end and start.date() == day and end.date() == day and start.hour >= 8 and end.hour >= 12:
        print(
            f"[garmin] {day.isoformat()}: sleep timestamps look daytime "
            f"({iso_minute(start)} -> {iso_minute(end)}). Anchoring to a normal overnight window from duration."
        )
        end = datetime.combine(day, DEFAULT_WAKE_TIME)
        start = end - timedelta(minutes=total)

    score = dig(payload, "sleepScores", "overall", "value") or daily.get("sleepScore")
    return {
        "date": day.isoformat(),
        "sleep_start": iso_minute(start) if start else None,
        "sleep_end": iso_minute(end),
        "total_sleep_minutes": total,
        "deep_minutes": to_minutes(daily.get("deepSleepSeconds")) or 0,
        "light_minutes": to_minutes(daily.get("lightSleepSeconds")) or 0,
        "rem_minutes": to_minutes(daily.get("remSleepSeconds")) or 0,
        "awake_minutes": to_minutes(daily.get("awakeSleepSeconds")) or 0,
        "nap_minutes": nap_minutes,
        "sleep_score": int(score) if score is not None else None,
        "source": "garmin",
    }


def extract_naps(day: date, payload: Dict[str, Any], fallback_minutes: int = 0) -> list[Dict[str, Any]]:
    """Extract Garmin nap totals/details when present.

    Garmin commonly exposes `napTimeSeconds` inside dailySleepDTO. Some payloads
    may include detailed nap records under nap-ish keys; we handle common field
    names and otherwise store an aggregate nap row with no start/end.
    """
    naps: list[Dict[str, Any]] = []

    def add_nap(start_value: Any, end_value: Any, duration_seconds: Any) -> None:
        start = parse_dt(start_value)
        end = parse_dt(end_value)
        duration = to_minutes(duration_seconds)
        if duration is None and start and end:
            duration = int((end - start).total_seconds() / 60)
        if not duration or duration <= 0:
            return
        naps.append({
            "date": day.isoformat(),
            "nap_start": iso_minute(start) if start else None,
            "nap_end": iso_minute(end) if end else None,
            "duration_minutes": duration,
            "source": "garmin",
        })

    for key in ["napSleepData", "napData", "naps", "napDTOList", "dailyNapDTOList"]:
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                add_nap(
                    item.get("napStartTimestampLocal") or item.get("sleepStartTimestampLocal") or item.get("startTimeLocal") or item.get("startTimeGMT"),
                    item.get("napEndTimestampLocal") or item.get("sleepEndTimestampLocal") or item.get("endTimeLocal") or item.get("endTimeGMT"),
                    item.get("napTimeSeconds") or item.get("durationSeconds") or item.get("sleepTimeSeconds"),
                )

    if not naps and fallback_minutes > 0:
        naps.append({
            "date": day.isoformat(),
            "nap_start": None,
            "nap_end": None,
            "duration_minutes": fallback_minutes,
            "source": "garmin",
        })
    return naps


def keys_preview(value: Any, limit: int = 12) -> str:
    if not isinstance(value, dict):
        return f"non-dict payload type={type(value).__name__}"
    keys = list(value.keys())
    suffix = "..." if len(keys) > limit else ""
    return ", ".join(str(k) for k in keys[:limit]) + suffix


def explain_sleep_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return f"expected dict, got {type(payload).__name__}"
    daily = payload.get("dailySleepDTO") or payload.get("dailySleepDto") or payload
    if not isinstance(daily, dict):
        return f"top-level keys=[{keys_preview(payload)}]; daily payload is {type(daily).__name__}"
    start = daily.get("sleepStartTimestampLocal") or daily.get("sleepStartTimestampGMT")
    end = daily.get("sleepEndTimestampLocal") or daily.get("sleepEndTimestampGMT")
    total = daily.get("sleepTimeSeconds") or daily.get("totalSleepTimeSeconds")
    return (
        f"top-level keys=[{keys_preview(payload)}]; "
        f"daily keys=[{keys_preview(daily)}]; "
        f"sleepStart={start!r}, sleepEnd={end!r}, sleepSeconds={total!r}"
    )


def log_exception(context: str, exc: Exception) -> None:
    print(f"[garmin] {context} failed: {type(exc).__name__}: {exc}")
    if os.environ.get("GARMIN_DEBUG") == "1":
        traceback.print_exc()


def build_mfa_prompt(mfa_code: Optional[str] = None):
    """Return a Garmin MFA callback for CLI use.

    python-garminconnect calls this callback when Garmin asks for a one-time MFA
    code. In non-interactive runs, such as the Go API invoking this script, we do
    not prompt because that would hang the API request.
    """
    if mfa_code:
        used = {"value": False}

        def prompt_from_value() -> str:
            if used["value"]:
                return ""
            used["value"] = True
            print("Using Garmin MFA code supplied via --mfa-code or GARMIN_MFA_CODE in .env.")
            return mfa_code.strip()

        return prompt_from_value

    if not sys.stdin.isatty():
        return None

    def prompt_from_cli() -> str:
        return input("Enter Garmin MFA code: ").strip()

    return prompt_from_cli


def try_garmin_client(mfa_code: Optional[str] = None) -> Optional[Any]:
    dotenv = load_dotenv()
    email = dotenv.get("GARMIN_EMAIL")
    password = dotenv.get("GARMIN_PASSWORD")
    mfa_code = mfa_code or dotenv.get("GARMIN_MFA_CODE")
    if not email or not password:
        print(f"GARMIN_EMAIL/GARMIN_PASSWORD not found in {DOTENV_PATH}; using mock data.")
        return None
    try:
        from garminconnect import Garmin  # type: ignore

        prompt_mfa = build_mfa_prompt(mfa_code)
        if prompt_mfa:
            print("Garmin MFA prompt enabled. If Garmin requests a code, enter it in this terminal.")
            client = Garmin(email, password, prompt_mfa=prompt_mfa)
        else:
            client = Garmin(email, password)
        client.login()
        print("Garmin login succeeded.")
        return client
    except Exception as exc:
        print(f"Garmin login failed; using mock data. Reason: {exc}")
        return None


def fetch_garmin_day(client: Any, day: date) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], list[Dict[str, Any]]]:
    day_s = day.isoformat()
    sleep_row: Optional[Dict[str, Any]] = None
    recovery_row: Optional[Dict[str, Any]] = None
    naps: list[Dict[str, Any]] = []

    print(f"[garmin] {day_s}: fetching sleep data...")
    try:
        sleep_payload = client.get_sleep_data(day_s)
        print(f"[garmin] {day_s}: sleep response received ({keys_preview(sleep_payload)}).")
        if isinstance(sleep_payload, dict):
            sleep_row = extract_sleep(day, sleep_payload)
            if sleep_row is None:
                print(f"[garmin] {day_s}: could not normalize sleep payload; using mock sleep. {explain_sleep_payload(sleep_payload)}")
            else:
                naps = extract_naps(day, sleep_payload, int(sleep_row.get("nap_minutes") or 0))
                print(
                    f"[garmin] {day_s}: normalized sleep "
                    f"{sleep_row['total_sleep_minutes']} min + naps {sleep_row.get('nap_minutes', 0)} min, "
                    f"score={sleep_row.get('sleep_score')}, "
                    f"window={sleep_row.get('sleep_start')} -> {sleep_row.get('sleep_end')}."
                )
        else:
            print(f"[garmin] {day_s}: unexpected sleep payload type {type(sleep_payload).__name__}; using mock sleep.")
    except Exception as exc:
        log_exception(f"{day_s}: sleep fetch", exc)
        print(f"[garmin] {day_s}: using mock sleep because Garmin sleep fetch failed.")

    stats: Dict[str, Any] = {}
    print(f"[garmin] {day_s}: fetching recovery stats...")
    try:
        stats_payload = client.get_stats(day_s)
        if isinstance(stats_payload, dict):
            stats = stats_payload
            print(f"[garmin] {day_s}: stats response received ({keys_preview(stats_payload)}).")
        else:
            print(f"[garmin] {day_s}: unexpected stats payload type {type(stats_payload).__name__}.")
    except Exception as exc:
        log_exception(f"{day_s}: stats fetch", exc)

    print(f"[garmin] {day_s}: fetching user summary...")
    try:
        summary = client.get_user_summary(day_s)
        if isinstance(summary, dict):
            print(f"[garmin] {day_s}: summary response received ({keys_preview(summary)}).")
            stats = {**stats, **summary}
        else:
            print(f"[garmin] {day_s}: unexpected summary payload type {type(summary).__name__}.")
    except Exception as exc:
        log_exception(f"{day_s}: user summary fetch", exc)

    if isinstance(stats, dict):
        body_start = stats.get("bodyBatteryMostRecentValue") or stats.get("bodyBatteryChargedValue")
        body_end = stats.get("bodyBatteryLowestValue") or stats.get("bodyBatteryDrainedValue")
        recovery_row = {
            "date": day_s,
            "resting_hr": stats.get("restingHeartRate") or stats.get("restingHeartRateInBeatsPerMinute"),
            "hrv_status": stats.get("hrvStatus") or stats.get("hrvStatusSummary") or "unknown",
            "stress_avg": stats.get("averageStressLevel") or stats.get("stressAverage") or stats.get("avgStressLevel"),
            "body_battery_start": body_start,
            "body_battery_end": body_end,
            "respiration_avg": stats.get("avgRespirationValue") or stats.get("averageRespiration"),
            "spo2_avg": stats.get("averageSpo2") or stats.get("avgSpo2"),
            "source": "garmin",
        }

    if recovery_row and all(recovery_row.get(k) is None for k in ["resting_hr", "stress_avg", "body_battery_start"]):
        print(
            f"[garmin] {day_s}: recovery payload had no usable resting_hr/stress/body_battery fields; "
            f"using mock recovery. merged keys=[{keys_preview(stats)}]"
        )
        recovery_row = None
    elif recovery_row:
        print(
            f"[garmin] {day_s}: normalized recovery "
            f"resting_hr={recovery_row.get('resting_hr')}, "
            f"stress={recovery_row.get('stress_avg')}, "
            f"body_battery={recovery_row.get('body_battery_start')}->{recovery_row.get('body_battery_end')}."
        )
    else:
        print(f"[garmin] {day_s}: no recovery stats available; using mock recovery.")
    if naps:
        print(f"[garmin] {day_s}: extracted {len(naps)} nap row(s), total {sum(int(n['duration_minutes']) for n in naps)} min.")
    return sleep_row, recovery_row, naps


def window_confidence(conn: sqlite3.Connection, day_s: str) -> str:
    rows = conn.execute(
        "SELECT source FROM daily_sleep WHERE date <= ? ORDER BY date DESC LIMIT 7", (day_s,)
    ).fetchall()
    if len(rows) >= 7 and all(row["source"] == "garmin" for row in rows):
        return "high"
    if any(row["source"] == "garmin" for row in rows):
        return "medium"
    return "low"


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def sleep_credit_minutes(row: Any) -> int:
    return int(row["total_sleep_minutes"] or 0) + int(row["nap_minutes"] or 0)


def daily_deficit(row: Any, sleep_need_minutes: int = SLEEP_NEED_MINUTES) -> int:
    return max(0, sleep_need_minutes - sleep_credit_minutes(row))


def daily_surplus(row: Any, sleep_need_minutes: int = SLEEP_NEED_MINUTES) -> int:
    return max(0, sleep_credit_minutes(row) - sleep_need_minutes)


def compute_acute_sleep_debt(rows: list[Any], sleep_need_minutes: int = SLEEP_NEED_MINUTES) -> int:
    """Recent positive sleep loss, capped so it cannot grow without bound."""
    return int(min(DEBT_CAP_MINUTES, sum(daily_deficit(row, sleep_need_minutes) for row in rows[-14:])))


def compute_decayed_sleep_debt(rows: list[Any], sleep_need_minutes: int = SLEEP_NEED_MINUTES) -> int:
    """Exponential sleep debt estimate.

    This is a product heuristic, not a medical model. Old deficits fade by 10%
    per day, surplus sleep pays down debt at 50% credit, and total debt is capped
    at 12 hours.
    """
    debt = 0.0
    for row in rows:
        debt = debt * 0.90
        debt += daily_deficit(row, sleep_need_minutes)
        debt -= daily_surplus(row, sleep_need_minutes) * 0.50
        debt = clamp(debt, 0, DEBT_CAP_MINUTES)
    return int(round(debt))


def compute_chronic_deficit(rows: list[Any], sleep_need_minutes: int = SLEEP_NEED_MINUTES) -> int:
    """Average nightly shortfall over up to 90 available days, not a total sum."""
    history = rows[-90:]
    if not history:
        return 0
    average_sleep = sum(sleep_credit_minutes(row) for row in history) / len(history)
    return int(round(max(0, sleep_need_minutes - average_sleep)))


def chronic_deficit_label(minutes_per_night: int) -> str:
    if minutes_per_night <= 15:
        return "none"
    if minutes_per_night <= 30:
        return "mild"
    if minutes_per_night <= 60:
        return "moderate"
    return "high"


def minute_of_day(value: Any, bedtime: bool = False) -> Optional[int]:
    dt = parse_dt(value)
    if not dt:
        return None
    minutes = dt.hour * 60 + dt.minute
    # Bedtimes shortly after midnight belong to the previous sleep evening for
    # consistency scoring, avoiding artificial midnight wraparound variance.
    if bedtime and minutes < 12 * 60:
        minutes += 24 * 60
    return minutes


def compute_sleep_consistency(rows: list[Any]) -> int:
    recent = rows[-14:]
    wake_times = [m for m in (minute_of_day(row["sleep_end"]) for row in recent) if m is not None]
    bedtimes = [m for m in (minute_of_day(row["sleep_start"], bedtime=True) for row in recent) if m is not None]
    score = 100
    if len(wake_times) >= 2:
        wake_std = statistics.pstdev(wake_times)
        if wake_std > 90:
            score -= 20
        elif wake_std > 45:
            score -= 10
    if len(bedtimes) >= 2:
        bedtime_std = statistics.pstdev(bedtimes)
        if bedtime_std > 120:
            score -= 20
        elif bedtime_std > 60:
            score -= 10
    return int(clamp(score, 0, 100))


def recovery_label(score: int) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "moderate"
    if score >= 30:
        return "low"
    return "poor"


def sleep_pressure_label(decayed_debt: int, chronic_deficit: int) -> str:
    if decayed_debt > 420 or chronic_deficit > 60:
        return "very high"
    if decayed_debt >= 240 or chronic_deficit >= 31:
        return "high"
    if decayed_debt >= 90 or chronic_deficit >= 15:
        return "moderate"
    return "low"


def resting_hr_baseline(recovery_rows: list[Any]) -> Optional[float]:
    values = [int(row["resting_hr"]) for row in recovery_rows[-60:] if row["resting_hr"] is not None]
    if len(values) < 7:
        return None
    return sum(values) / len(values)


def compute_recovery_score(
    decayed_debt: int,
    chronic_deficit: int,
    consistency_score: int,
    current_recovery: Optional[Any],
    recovery_history: list[Any],
) -> int:
    score = 100.0
    score -= (decayed_debt / DEBT_CAP_MINUTES) * 35
    score -= min(20, (chronic_deficit / 90) * 20)
    if consistency_score < 70:
        score -= 10

    if current_recovery:
        stress = current_recovery["stress_avg"]
        if stress is not None and float(stress) > 60:
            score -= 10

        baseline = resting_hr_baseline(recovery_history[:-1])
        resting_hr = current_recovery["resting_hr"]
        if baseline is not None and resting_hr is not None and float(resting_hr) > baseline + 5:
            score -= 10

        body_battery_start = current_recovery["body_battery_start"]
        if body_battery_start is not None and float(body_battery_start) < 50:
            score -= 10

        hrv_status = str(current_recovery["hrv_status"] or "").lower()
        if hrv_status in {"low", "unbalanced"}:
            score -= 10

    return int(round(clamp(score, 0, 100)))


def adjusted_confidence(base: str, chronic_deficit: int, recovery_score_value: int) -> str:
    levels = ["low", "medium", "high"]
    confidence = base if base in levels else "low"
    idx = levels.index(confidence)
    if chronic_deficit > 45:
        idx = max(0, idx - 1)
    if recovery_score_value < 50:
        idx = 0
    return levels[idx]


def compute_inertia_minutes(decayed_debt: int, last_night_sleep_minutes: int) -> int:
    inertia = 60
    if decayed_debt > 300:
        inertia = 120
    elif decayed_debt > 180:
        inertia = 90
    if last_night_sleep_minutes < 390:
        inertia = max(inertia, 90)
    return int(min(120, inertia))


def compute_dynamic_wake_span_minutes(decayed_debt: int, recovery_score_value: int, chronic_deficit: int) -> int:
    """Estimated wake span before target bedtime.

    Base phase is later than the original MVP (17h after wake), then moves
    earlier with high pressure. This is a product heuristic calibrated against a
    RISE-like example, not a circadian/medical model.
    """
    span = 17 * 60
    if decayed_debt > 300:
        span -= 60
    elif decayed_debt > 180:
        span -= 30
    if recovery_score_value < 50:
        span -= 30
    if chronic_deficit > 45:
        span -= 30
    return int(clamp(span, 15 * 60 + 45, 17 * 60 + 30))


def compute_chronic_deficit_repay_minutes(chronic_deficit: int) -> int:
    if chronic_deficit < 15:
        return 0
    if chronic_deficit <= 30:
        return 15
    if chronic_deficit <= 60:
        return 30
    return 45


def compute_recovery_penalty_minutes(recovery_score_value: int) -> int:
    if recovery_score_value < 50:
        return 30
    if recovery_score_value <= 70:
        return 15
    return 0


def compute_next_day_sleep_need(
    decayed_debt: int,
    chronic_deficit: int,
    nap_credit: int,
    recovery_score_value: int,
    base_sleep_need: int = SLEEP_NEED_MINUTES,
) -> Dict[str, int]:
    nap_credit = int(min(60, max(0, nap_credit)))
    acute_repay = int(round(min(decayed_debt * 0.25, 90)))
    chronic_repay = compute_chronic_deficit_repay_minutes(chronic_deficit)
    recovery_penalty = compute_recovery_penalty_minutes(recovery_score_value)
    adjustment = acute_repay + chronic_repay - nap_credit + recovery_penalty
    next_need = int(clamp(base_sleep_need + adjustment, 450, 630))
    return {
        "base_sleep_need_minutes": base_sleep_need,
        "next_day_sleep_need_minutes": next_need,
        "sleep_need_adjustment_minutes": next_need - base_sleep_need,
        "acute_debt_repay_minutes": acute_repay,
        "chronic_deficit_repay_minutes": chronic_repay,
        "nap_credit_minutes": nap_credit,
        "recovery_penalty_minutes": recovery_penalty,
    }


def nap_start_is_eligible(nap_start: Any) -> bool:
    dt = parse_dt(nap_start)
    if not dt:
        return False
    minutes = dt.hour * 60 + dt.minute
    return 10 * 60 <= minutes < 17 * 60


def compute_nap_credit_minutes(nap_rows: list[Any], fallback_nap_minutes: int) -> int:
    """Partial next-day sleep need credit from naps.

    Timed nap data only counts if the nap starts between 10:00 and 17:00. If
    only aggregate nap minutes exist, use that aggregate. Credit is 60% of
    eligible nap minutes, capped at 60 minutes.
    """
    eligible_minutes = 0
    timed_rows = [row for row in nap_rows if row["nap_start"]]
    if timed_rows:
        eligible_minutes = sum(
            int(row["duration_minutes"] or 0) for row in timed_rows if nap_start_is_eligible(row["nap_start"])
        )
    elif nap_rows:
        eligible_minutes = sum(int(row["duration_minutes"] or 0) for row in nap_rows)
    else:
        eligible_minutes = fallback_nap_minutes
    return int(round(min(60, eligible_minutes * 0.6)))


def recompute_energy(conn: sqlite3.Connection) -> None:
    """Compute estimated energy windows from sleep, recovery, and pressure.

    This is a simple product heuristic, not medical advice. Acute debt is capped
    and decays; chronic sleep restriction is represented separately as average
    nightly deficit.
    """
    sleep_rows = conn.execute("SELECT * FROM daily_sleep ORDER BY date").fetchall()
    recovery_rows = conn.execute("SELECT * FROM daily_recovery ORDER BY date").fetchall()
    recovery_by_date = {row["date"]: row for row in recovery_rows}

    for idx, row in enumerate(sleep_rows):
        day_s = row["date"]
        day = date.fromisoformat(day_s)
        wake = parse_dt(row["sleep_end"]) or datetime.combine(day, DEFAULT_WAKE_TIME)
        sleep_history = sleep_rows[: idx + 1]
        recovery_history = [r for r in recovery_rows if r["date"] <= day_s]
        current_recovery = recovery_by_date.get(day_s)

        acute_debt = compute_acute_sleep_debt(sleep_history)
        decayed_debt = compute_decayed_sleep_debt(sleep_history)
        chronic_deficit = compute_chronic_deficit(sleep_history)
        consistency = compute_sleep_consistency(sleep_history)
        recovery_score_value = compute_recovery_score(
            decayed_debt, chronic_deficit, consistency, current_recovery, recovery_history
        )
        pressure = sleep_pressure_label(decayed_debt, chronic_deficit)
        recovery_label_value = recovery_label(recovery_score_value)
        chronic_label = chronic_deficit_label(chronic_deficit)

        nap_rows = conn.execute("SELECT * FROM daily_naps WHERE date = ?", (day_s,)).fetchall()
        nap_credit = compute_nap_credit_minutes(nap_rows, int(row["nap_minutes"] or 0))
        sleep_need = compute_next_day_sleep_need(decayed_debt, chronic_deficit, nap_credit, recovery_score_value)
        dynamic_wake_span = compute_dynamic_wake_span_minutes(decayed_debt, recovery_score_value, chronic_deficit)

        groggy_minutes = compute_inertia_minutes(decayed_debt, int(row["total_sleep_minutes"] or 0))

        morning_start = wake + timedelta(hours=2, minutes=45)
        morning_end = wake + timedelta(hours=5, minutes=55)
        afternoon_start = wake + timedelta(hours=8)
        afternoon_end = wake + timedelta(hours=10, minutes=5)
        evening_start = wake + timedelta(hours=12, minutes=10)
        evening_end = wake + timedelta(hours=15, minutes=2)

        target_bedtime = wake + timedelta(minutes=dynamic_wake_span)
        wind_down = target_bedtime - timedelta(hours=1, minutes=34)
        mel_start = target_bedtime
        mel_end = target_bedtime + timedelta(hours=1)
        confidence = adjusted_confidence(window_confidence(conn, day_s), chronic_deficit, recovery_score_value)

        explanation = (
            f"{MODEL_VERSION}: phase windows use calibrated offsets from wake; target bedtime uses a dynamic wake span; "
            f"next-day sleep need starts at {SLEEP_NEED_MINUTES} min and adjusts for decayed debt, chronic deficit, naps, and recovery. Estimates only."
        )

        values = {
            "date": day_s,
            "wake_time": iso_minute(wake),
            "grogginess_start": iso_minute(wake),
            "grogginess_end": iso_minute(wake + timedelta(minutes=groggy_minutes)),
            "morning_peak_start": iso_minute(morning_start),
            "morning_peak_end": iso_minute(morning_end),
            "afternoon_dip_start": iso_minute(afternoon_start),
            "afternoon_dip_end": iso_minute(afternoon_end),
            "evening_peak_start": iso_minute(evening_start),
            "evening_peak_end": iso_minute(evening_end),
            "wind_down_start": iso_minute(wind_down),
            "target_bedtime": iso_minute(target_bedtime),
            "melatonin_window_start": iso_minute(mel_start),
            "melatonin_window_end": iso_minute(mel_end),
            "sleep_debt_minutes": decayed_debt,
            "acute_sleep_debt_minutes": acute_debt,
            "chronic_sleep_deficit_minutes_per_night": chronic_deficit,
            "chronic_deficit_label": chronic_label,
            "decayed_sleep_debt_minutes": decayed_debt,
            "sleep_consistency_score": consistency,
            "recovery_score": recovery_score_value,
            "recovery_label": recovery_label_value,
            "sleep_pressure_label": pressure,
            "model_version": MODEL_VERSION,
            "calculation_explanation": explanation,
            **sleep_need,
            "dynamic_wake_span_minutes": dynamic_wake_span,
            "confidence": confidence,
        }
        conn.execute(
            """
            INSERT INTO energy_windows (
                date, wake_time, grogginess_start, grogginess_end,
                morning_peak_start, morning_peak_end, afternoon_dip_start,
                afternoon_dip_end, evening_peak_start, evening_peak_end,
                wind_down_start, target_bedtime, melatonin_window_start,
                melatonin_window_end, sleep_debt_minutes, acute_sleep_debt_minutes,
                chronic_sleep_deficit_minutes_per_night, chronic_deficit_label,
                decayed_sleep_debt_minutes, sleep_consistency_score, recovery_score,
                recovery_label, sleep_pressure_label, model_version,
                calculation_explanation, base_sleep_need_minutes,
                next_day_sleep_need_minutes, sleep_need_adjustment_minutes,
                acute_debt_repay_minutes, chronic_deficit_repay_minutes,
                nap_credit_minutes, recovery_penalty_minutes,
                dynamic_wake_span_minutes, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                wake_time=excluded.wake_time,
                grogginess_start=excluded.grogginess_start,
                grogginess_end=excluded.grogginess_end,
                morning_peak_start=excluded.morning_peak_start,
                morning_peak_end=excluded.morning_peak_end,
                afternoon_dip_start=excluded.afternoon_dip_start,
                afternoon_dip_end=excluded.afternoon_dip_end,
                evening_peak_start=excluded.evening_peak_start,
                evening_peak_end=excluded.evening_peak_end,
                wind_down_start=excluded.wind_down_start,
                target_bedtime=excluded.target_bedtime,
                melatonin_window_start=excluded.melatonin_window_start,
                melatonin_window_end=excluded.melatonin_window_end,
                sleep_debt_minutes=excluded.sleep_debt_minutes,
                acute_sleep_debt_minutes=excluded.acute_sleep_debt_minutes,
                chronic_sleep_deficit_minutes_per_night=excluded.chronic_sleep_deficit_minutes_per_night,
                chronic_deficit_label=excluded.chronic_deficit_label,
                decayed_sleep_debt_minutes=excluded.decayed_sleep_debt_minutes,
                sleep_consistency_score=excluded.sleep_consistency_score,
                recovery_score=excluded.recovery_score,
                recovery_label=excluded.recovery_label,
                sleep_pressure_label=excluded.sleep_pressure_label,
                model_version=excluded.model_version,
                calculation_explanation=excluded.calculation_explanation,
                base_sleep_need_minutes=excluded.base_sleep_need_minutes,
                next_day_sleep_need_minutes=excluded.next_day_sleep_need_minutes,
                sleep_need_adjustment_minutes=excluded.sleep_need_adjustment_minutes,
                acute_debt_repay_minutes=excluded.acute_debt_repay_minutes,
                chronic_deficit_repay_minutes=excluded.chronic_deficit_repay_minutes,
                nap_credit_minutes=excluded.nap_credit_minutes,
                recovery_penalty_minutes=excluded.recovery_penalty_minutes,
                dynamic_wake_span_minutes=excluded.dynamic_wake_span_minutes,
                confidence=excluded.confidence
            """,
            tuple(values.values()),
        )
    conn.commit()


def date_range(end_day: date, days: int) -> Iterable[date]:
    start = end_day - timedelta(days=days - 1)
    for idx in range(days):
        yield start + timedelta(days=idx)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Garmin health data or seed mock Recovery IQ data.")
    parser.add_argument("--date", default=date.today().isoformat(), help="End date, YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=30, help="Number of days ending on --date")
    parser.add_argument("--mfa-code", help="Optional one-time Garmin MFA code. If omitted in a terminal, you will be prompted when Garmin asks for MFA.")
    args = parser.parse_args()

    end_day = date.fromisoformat(args.date)
    days = max(1, int(args.days))

    conn = connect_db()
    ensure_schema(conn)

    client = try_garmin_client(args.mfa_code)
    if client is not None:
        print(f"[garmin] Starting Garmin fetch for {days} day(s), ending {end_day.isoformat()}.")
    inserted = 0
    garmin_count = 0

    for day in date_range(end_day, days):
        mock_sleep, mock_recovery, mock_naps = mock_day(day)
        sleep_row: Optional[Dict[str, Any]] = None
        recovery_row: Optional[Dict[str, Any]] = None
        naps: list[Dict[str, Any]] = []

        if client is not None:
            sleep_row, recovery_row, naps = fetch_garmin_day(client, day)

        if sleep_row is None:
            sleep_row = mock_sleep
            naps = mock_naps
        else:
            garmin_count += 1

        if recovery_row is None:
            recovery_row = mock_recovery
        else:
            # Fill any missing Garmin fields with same-day mock values for a stable UI.
            for key, value in mock_recovery.items():
                if recovery_row.get(key) is None:
                    recovery_row[key] = value
            recovery_row["source"] = "garmin"

        upsert_sleep(conn, sleep_row)
        replace_naps(conn, day.isoformat(), naps)
        upsert_recovery(conn, recovery_row)
        inserted += 1

    conn.commit()
    recompute_energy(conn)
    conn.close()
    print(f"Synced {inserted} days to {DB_PATH} ({garmin_count} Garmin sleep rows, {inserted - garmin_count} mock sleep rows).")


if __name__ == "__main__":
    main()
