import { Card, Group, Stack, Text, Title } from '@mantine/core';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { DailySleep } from '../types';
import { shortDate, tooltipFixed2 } from '../format';

export function SleepTrend({ rows }: { rows: DailySleep[] }) {
  const data = rows.map((row) => ({
    date: shortDate(row.date),
    hours: Number((row.total_sleep_minutes / 60).toFixed(2)),
    score: row.sleep_score,
    deep: Number((row.deep_minutes / 60).toFixed(2)),
    rem: Number((row.rem_minutes / 60).toFixed(2)),
    naps: Number(((row.nap_minutes ?? 0) / 60).toFixed(2)),
  }));

  return (
    <Stack gap="md">
      <Card withBorder radius="lg" p="lg">
        <Group justify="space-between" mb="md">
          <div>
            <Title order={3}>Sleep trend</Title>
            <Text size="sm" c="dimmed">Last 30 days, Garmin data where available and mock otherwise.</Text>
          </div>
        </Group>
        <div style={{ height: 340 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ left: 4, right: 16, top: 8, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" minTickGap={24} />
              <YAxis yAxisId="left" domain={[0, 10]} label={{ value: 'Hours', angle: -90, position: 'insideLeft' }} />
              <YAxis yAxisId="right" orientation="right" domain={[0, 100]} label={{ value: 'Score', angle: 90, position: 'insideRight' }} />
              <Tooltip formatter={tooltipFixed2} />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="hours" name="Total sleep" stroke="#4c6ef5" strokeWidth={3} dot={false} />
              <Line yAxisId="left" type="monotone" dataKey="deep" name="Deep" stroke="#15aabf" dot={false} />
              <Line yAxisId="left" type="monotone" dataKey="rem" name="REM" stroke="#be4bdb" dot={false} />
              <Line yAxisId="left" type="monotone" dataKey="naps" name="Naps" stroke="#f59f00" dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="score" name="Sleep score" stroke="#40c057" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </Stack>
  );
}
