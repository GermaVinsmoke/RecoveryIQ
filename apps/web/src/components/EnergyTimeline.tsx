import { Badge, Card, Grid, Group, Stack, Text, Timeline, Title } from '@mantine/core';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { EnergyWindows } from '../types';
import { clock, hours, range, shortDate, tooltipFixed2 } from '../format';

export function EnergyTimeline({ rows }: { rows: EnergyWindows[] }) {
  const current = rows[rows.length - 1];
  const data = rows.map((row) => ({
    date: shortDate(row.date),
    debt: Number(((row.decayed_sleep_debt_minutes ?? row.sleep_debt_minutes) / 60).toFixed(2)),
    chronic: Number(((row.chronic_sleep_deficit_minutes_per_night ?? 0) / 60).toFixed(2)),
  }));

  if (!current) return <Text>No energy window data found.</Text>;

  return (
    <Stack gap="md">
      <Grid>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Card withBorder radius="lg" p="lg" h="100%">
            <Group justify="space-between" mb="md">
              <Title order={3}>Today’s timeline</Title>
              <Badge color={current.confidence === 'high' ? 'green' : current.confidence === 'medium' ? 'yellow' : 'gray'}>{current.confidence}</Badge>
            </Group>
            <Timeline active={5} bulletSize={24} lineWidth={2}>
              <Timeline.Item title="Wake / grogginess">
                <Text size="sm">{range(current.grogginess_start, current.grogginess_end)}</Text>
              </Timeline.Item>
              <Timeline.Item title="Morning productivity peak">
                <Text size="sm">{range(current.morning_peak_start, current.morning_peak_end)}</Text>
              </Timeline.Item>
              <Timeline.Item title="Afternoon dip">
                <Text size="sm">{range(current.afternoon_dip_start, current.afternoon_dip_end)}</Text>
              </Timeline.Item>
              <Timeline.Item title="Evening peak">
                <Text size="sm">{range(current.evening_peak_start, current.evening_peak_end)}</Text>
                {current.recovery_score < 50 && <Text size="xs" c="dimmed">Lower confidence when recovery is low.</Text>}
              </Timeline.Item>
              <Timeline.Item title="Wind-down">
                <Text size="sm">Start around {clock(current.wind_down_start)}</Text>
              </Timeline.Item>
              <Timeline.Item title="Estimated melatonin window">
                <Text size="sm">{range(current.melatonin_window_start, current.melatonin_window_end)}</Text>
              </Timeline.Item>
            </Timeline>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Card withBorder radius="lg" p="lg" h="100%">
            <Title order={3}>Sleep pressure trend</Title>
            <Text size="sm" c="dimmed" mb="md">
              Decayed debt: {hours(current.decayed_sleep_debt_minutes ?? current.sleep_debt_minutes)} · Chronic deficit: {current.chronic_sleep_deficit_minutes_per_night ?? 0} min/night
            </Text>
            <div style={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ left: 0, right: 16, top: 8, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis label={{ value: 'Hours', angle: -90, position: 'insideLeft' }} />
                  <Tooltip formatter={tooltipFixed2} />
                  <Area type="monotone" dataKey="debt" name="Decayed debt (h)" stroke="#7950f2" fill="#d0bfff" />
                  <Area type="monotone" dataKey="chronic" name="Chronic deficit (h/night)" stroke="#f08c00" fill="#ffe8cc" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
