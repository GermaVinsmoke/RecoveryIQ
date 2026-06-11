export function hours(minutes?: number) {
  if (minutes === undefined || minutes === null || Number.isNaN(minutes)) return '—';
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return `${h}h ${m}m`;
}

export function clock(value?: string) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function range(start?: string, end?: string) {
  return `${clock(start)} – ${clock(end)}`;
}

export function shortDate(value: string) {
  const d = new Date(`${value}T12:00:00`);
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export function fixed2(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  return value.toFixed(2);
}

export function tooltipFixed2(value: unknown): string {
  return typeof value === 'number' ? value.toFixed(2) : String(value ?? '—');
}
