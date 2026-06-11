import sqlite3
import unittest
from datetime import date, datetime, time, timedelta

import sync


def row(total: int, nap: int = 0, day: date = date(2026, 1, 1), wake_hour: int = 7, wake_minute: int = 0):
    wake = datetime.combine(day, time(wake_hour, wake_minute))
    return {
        "date": day.isoformat(),
        "sleep_start": (wake - timedelta(minutes=total)).isoformat(timespec="minutes"),
        "sleep_end": wake.isoformat(timespec="minutes"),
        "total_sleep_minutes": total,
        "nap_minutes": nap,
    }


class SleepEngineTests(unittest.TestCase):
    def test_debt_does_not_grow_above_cap(self):
        rows = [row(0, day=date(2026, 1, 1) + timedelta(days=i)) for i in range(20)]
        self.assertEqual(sync.compute_acute_sleep_debt(rows), sync.DEBT_CAP_MINUTES)
        self.assertEqual(sync.compute_decayed_sleep_debt(rows), sync.DEBT_CAP_MINUTES)

    def test_debt_decays_over_time(self):
        rows = [row(sync.SLEEP_NEED_MINUTES - 300)]
        rows += [row(sync.SLEEP_NEED_MINUTES, day=date(2026, 1, 2) + timedelta(days=i)) for i in range(5)]
        self.assertLess(sync.compute_decayed_sleep_debt(rows), 300)
        self.assertGreater(sync.compute_decayed_sleep_debt(rows), 0)

    def test_surplus_sleep_reduces_debt_partially(self):
        rows = [row(sync.SLEEP_NEED_MINUTES - 300), row(sync.SLEEP_NEED_MINUTES + 120)]
        self.assertEqual(sync.compute_decayed_sleep_debt(rows), 210)

    def test_chronic_deficit_uses_average_not_total_sum(self):
        rows = [row(sync.SLEEP_NEED_MINUTES - 30, day=date(2026, 1, 1) + timedelta(days=i)) for i in range(10)]
        self.assertEqual(sync.compute_chronic_deficit(rows), 30)

    def test_recovery_score_clamps_0_to_100(self):
        current = {
            "stress_avg": 90,
            "resting_hr": 80,
            "body_battery_start": 20,
            "hrv_status": "low",
        }
        history = [{"resting_hr": 55, **current} for _ in range(10)] + [current]
        score = sync.compute_recovery_score(720, 120, 50, current, history)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_labels_map_correctly(self):
        self.assertEqual(sync.recovery_label(90), "excellent")
        self.assertEqual(sync.recovery_label(75), "good")
        self.assertEqual(sync.recovery_label(55), "moderate")
        self.assertEqual(sync.recovery_label(40), "low")
        self.assertEqual(sync.recovery_label(10), "poor")
        self.assertEqual(sync.sleep_pressure_label(80, 10), "low")
        self.assertEqual(sync.sleep_pressure_label(120, 10), "moderate")
        self.assertEqual(sync.sleep_pressure_label(300, 10), "high")
        self.assertEqual(sync.sleep_pressure_label(500, 10), "very high")

    def test_energy_windows_shift_under_high_debt(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        sync.ensure_schema(conn)
        for i in range(10):
            day = date(2026, 1, 1) + timedelta(days=i)
            sleep = row(300, day=day)
            sleep.update({
                "deep_minutes": 60,
                "light_minutes": 180,
                "rem_minutes": 60,
                "awake_minutes": 10,
                "sleep_score": 60,
                "source": "mock",
            })
            recovery = {
                "date": day.isoformat(),
                "resting_hr": 55,
                "hrv_status": "balanced",
                "stress_avg": 30,
                "body_battery_start": 80,
                "body_battery_end": 40,
                "respiration_avg": 14,
                "spo2_avg": 98,
                "source": "mock",
            }
            sync.upsert_sleep(conn, sleep)
            sync.upsert_recovery(conn, recovery)
        conn.commit()
        sync.recompute_energy(conn)
        energy = conn.execute("SELECT * FROM energy_windows ORDER BY date DESC LIMIT 1").fetchone()
        wake = sync.parse_dt(energy["wake_time"])
        groggy_end = sync.parse_dt(energy["grogginess_end"])
        target_bedtime = sync.parse_dt(energy["target_bedtime"])
        self.assertEqual(int((groggy_end - wake).total_seconds() / 60), 120)
        self.assertEqual(target_bedtime, wake + timedelta(hours=15, minutes=45))
        self.assertGreaterEqual(energy["decayed_sleep_debt_minutes"], 300)
        conn.close()

    def test_wake_0757_produces_rise_like_windows(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        sync.ensure_schema(conn)
        for i in range(89):
            day = date(2026, 1, 1) + timedelta(days=i)
            sleep = row(sync.SLEEP_NEED_MINUTES, day=day, wake_hour=7, wake_minute=57)
            sleep.update({"deep_minutes": 80, "light_minutes": 300, "rem_minutes": 100, "awake_minutes": 10, "sleep_score": 85, "source": "mock"})
            recovery = {"date": day.isoformat(), "resting_hr": 55, "hrv_status": "balanced", "stress_avg": 30, "body_battery_start": 80, "body_battery_end": 40, "respiration_avg": 14, "spo2_avg": 98, "source": "mock"}
            sync.upsert_sleep(conn, sleep)
            sync.upsert_recovery(conn, recovery)
        day = date(2026, 3, 31)
        sleep = row(380, day=day, wake_hour=7, wake_minute=57)
        sleep.update({"deep_minutes": 60, "light_minutes": 240, "rem_minutes": 80, "awake_minutes": 10, "sleep_score": 70, "source": "mock"})
        recovery = {"date": day.isoformat(), "resting_hr": 55, "hrv_status": "balanced", "stress_avg": 30, "body_battery_start": 80, "body_battery_end": 40, "respiration_avg": 14, "spo2_avg": 98, "source": "mock"}
        sync.upsert_sleep(conn, sleep)
        sync.upsert_recovery(conn, recovery)
        conn.commit()
        sync.recompute_energy(conn)
        energy = conn.execute("SELECT * FROM energy_windows ORDER BY date DESC LIMIT 1").fetchone()
        self.assertEqual(energy["grogginess_start"], "2026-03-31T07:57")
        self.assertEqual(energy["grogginess_end"], "2026-03-31T09:27")
        self.assertEqual(energy["morning_peak_start"], "2026-03-31T10:42")
        self.assertEqual(energy["morning_peak_end"], "2026-03-31T13:52")
        self.assertEqual(energy["afternoon_dip_start"], "2026-03-31T15:57")
        self.assertEqual(energy["evening_peak_start"], "2026-03-31T20:07")
        self.assertEqual(energy["target_bedtime"], "2026-04-01T00:57")
        self.assertEqual(energy["wind_down_start"], "2026-03-31T23:23")
        self.assertEqual(energy["melatonin_window_start"], energy["target_bedtime"])
        self.assertEqual(energy["melatonin_window_end"], "2026-04-01T01:57")
        conn.close()

    def test_phase_offsets_are_later_than_old_model(self):
        wake = datetime(2026, 1, 1, 7, 57)
        self.assertEqual(wake + timedelta(hours=8), datetime(2026, 1, 1, 15, 57))
        self.assertEqual(wake + timedelta(hours=12, minutes=10), datetime(2026, 1, 1, 20, 7))

    def test_dynamic_sleep_need_increases_with_debt(self):
        result = sync.compute_next_day_sleep_need(360, 0, 0, 90)
        self.assertGreater(result["next_day_sleep_need_minutes"], result["base_sleep_need_minutes"])
        self.assertGreater(result["acute_debt_repay_minutes"], 0)

    def test_naps_reduce_next_day_sleep_need_partially(self):
        no_nap = sync.compute_next_day_sleep_need(240, 30, 0, 80)
        with_nap = sync.compute_next_day_sleep_need(240, 30, 30, 80)
        self.assertEqual(no_nap["next_day_sleep_need_minutes"] - with_nap["next_day_sleep_need_minutes"], 30)
        nap_rows = [{"nap_start": "2026-01-01T14:00", "duration_minutes": 45}]
        self.assertEqual(sync.compute_nap_credit_minutes(nap_rows, 0), 27)

    def test_dynamic_sleep_need_clamps(self):
        high = sync.compute_next_day_sleep_need(720, 120, 0, 30)
        low = sync.compute_next_day_sleep_need(0, 0, 600, 95)
        self.assertEqual(high["next_day_sleep_need_minutes"], 630)
        self.assertEqual(low["next_day_sleep_need_minutes"], 450)

    def test_fixed_sleep_need_is_not_final_displayed_need(self):
        result = sync.compute_next_day_sleep_need(360, 45, 0, 60)
        self.assertEqual(result["base_sleep_need_minutes"], sync.SLEEP_NEED_MINUTES)
        self.assertNotEqual(result["next_day_sleep_need_minutes"], sync.SLEEP_NEED_MINUTES)


if __name__ == "__main__":
    unittest.main()
