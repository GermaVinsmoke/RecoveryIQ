import { Card, Grid, Group, Stack, Text, Title } from '@mantine/core';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { DailyRecovery } from '../types';
import { fixed2, shortDate, tooltipFixed2 } from '../format';

function latest<T>(rows: T[]): T | undefined {
  return rows[rows.length - 1];
}

export function RecoveryCards({ rows }: { rows: DailyRecovery[] }) {
  const current = latest(rows);
  const data = rows.map((row) => ({
    date: shortDate(row.date),
    resting_hr: row.resting_hr,
    stress_avg: row.stress_avg,
    body_battery_start: row.body_battery_start,
    body_battery_end: row.body_battery_end,
  }));

  return (
    <Stack gap="md">
      <Grid>
        <Grid.Col span={{ base: 6, md: 3 }}><Card withBorder radius="lg"><Text c="dimmed" size="sm">Resting HR</Text><Title order={3}>{current?.resting_hr ?? '—'} bpm</Title></Card></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><Card withBorder radius="lg"><Text c="dimmed" size="sm">Stress avg</Text><Title order={3}>{current?.stress_avg ?? '—'}</Title></Card></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><Card withBorder radius="lg"><Text c="dimmed" size="sm">Body Battery</Text><Title order={3}>{current ? `${current.body_battery_start} → ${current.body_battery_end}` : '—'}</Title></Card></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><Card withBorder radius="lg"><Text c="dimmed" size="sm">SpO₂ avg</Text><Title order={3}>{current?.spo2_avg === undefined ? '—' : `${fixed2(current.spo2_avg)}%`}</Title></Card></Grid.Col>
      </Grid>

      <Card withBorder radius="lg" p="lg">
        <Group justify="space-between" mb="md">
          <div>
            <Title order={3}>Recovery trends</Title>
            <Text size="sm" c="dimmed">Resting heart rate, stress, and body battery estimates.</Text>
          </div>
        </Group>
        <div style={{ height: 340 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ left: 4, right: 16, top: 8, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" minTickGap={24} />
              <YAxis domain={[0, 100]} />
              <Tooltip formatter={tooltipFixed2} />
              <Legend />
              <Line type="monotone" dataKey="resting_hr" name="Resting HR" stroke="#fa5252" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="stress_avg" name="Stress" stroke="#fd7e14" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="body_battery_start" name="Body Battery start" stroke="#40c057" dot={false} />
              <Line type="monotone" dataKey="body_battery_end" name="Body Battery end" stroke="#228be6" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </Stack>
  );
}
