import type { DailyRecovery, DailySleep, EnergyWindows, TodayResponse } from './types';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  today: () => request<TodayResponse>('/api/today'),
  sleep: (days = 30) => request<DailySleep[]>(`/api/sleep?days=${days}`),
  recovery: (days = 30) => request<DailyRecovery[]>(`/api/recovery?days=${days}`),
  energy: (days = 14) => request<EnergyWindows[]>(`/api/energy?days=${days}`),
  sync: (days = 14) => request<{ ok: boolean; output: string }>(`/api/sync?days=${days}`, { method: 'POST' }),
};
