export type SleepModelFields = {
  acute_sleep_debt_minutes?: number;
  chronic_sleep_deficit_minutes_per_night?: number;
  chronic_deficit_label?: string;
  decayed_sleep_debt_minutes?: number;
  sleep_consistency_score?: number;
  recovery_score?: number;
  recovery_label?: string;
  sleep_pressure_label?: string;
  model_version?: string;
  calculation_explanation?: string;
  base_sleep_need_minutes?: number;
  next_day_sleep_need_minutes?: number;
  sleep_need_adjustment_minutes?: number;
  acute_debt_repay_minutes?: number;
  chronic_deficit_repay_minutes?: number;
  nap_credit_minutes?: number;
  recovery_penalty_minutes?: number;
  dynamic_wake_span_minutes?: number;
};

export type DailySleep = SleepModelFields & {
  date: string;
  sleep_start: string;
  sleep_end: string;
  total_sleep_minutes: number;
  deep_minutes: number;
  light_minutes: number;
  rem_minutes: number;
  awake_minutes: number;
  nap_minutes: number;
  sleep_score: number;
  source: string;
};

export type DailyRecovery = SleepModelFields & {
  date: string;
  resting_hr: number;
  hrv_status: string;
  stress_avg: number;
  body_battery_start: number;
  body_battery_end: number;
  respiration_avg: number;
  spo2_avg: number;
  source: string;
};

export type EnergyWindows = {
  date: string;
  wake_time: string;
  grogginess_start: string;
  grogginess_end: string;
  morning_peak_start: string;
  morning_peak_end: string;
  afternoon_dip_start: string;
  afternoon_dip_end: string;
  evening_peak_start: string;
  evening_peak_end: string;
  wind_down_start: string;
  target_bedtime: string;
  melatonin_window_start: string;
  melatonin_window_end: string;
  sleep_debt_minutes: number;
  acute_sleep_debt_minutes: number;
  chronic_sleep_deficit_minutes_per_night: number;
  chronic_deficit_label: string;
  decayed_sleep_debt_minutes: number;
  sleep_consistency_score: number;
  recovery_score: number;
  recovery_label: string;
  sleep_pressure_label: string;
  model_version: string;
  calculation_explanation?: string;
  base_sleep_need_minutes: number;
  next_day_sleep_need_minutes: number;
  sleep_need_adjustment_minutes: number;
  acute_debt_repay_minutes: number;
  chronic_deficit_repay_minutes: number;
  nap_credit_minutes: number;
  recovery_penalty_minutes: number;
  dynamic_wake_span_minutes: number;
  confidence: string;
};

export type DailyNap = {
  id: number;
  date: string;
  nap_start?: string | null;
  nap_end?: string | null;
  duration_minutes: number;
  source: string;
};

export type TodayResponse = {
  date: string;
  sleep: DailySleep;
  naps?: DailyNap[];
  recovery: DailyRecovery;
  energy: EnergyWindows;
  disclaimer: string;
};
