import { useState } from 'react';
import { ActionIcon, Alert, Badge, Card, Grid, Group, List, Modal, Progress, RingProgress, Stack, Text, Title } from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import type { TodayResponse } from '../types';
import { hours, range } from '../format';

type Props = {
  today: TodayResponse;
};

function recommendations(today: TodayResponse) {
  const energy = today.energy;
  const stress = today.recovery?.stress_avg ?? 0;
  const items: string[] = [];

  if ((energy.recovery_score ?? 100) < 50) {
    items.push('Avoid HIIT/heavy training today. Prefer walking, mobility, or light zone-2.');
  }
  if ((energy.decayed_sleep_debt_minutes ?? energy.sleep_debt_minutes ?? 0) > 300) {
    items.push('Expect longer sleep inertia/grogginess. Delay deep work if possible.');
  }
  if ((energy.chronic_sleep_deficit_minutes_per_night ?? 0) > 45) {
    items.push('You are chronically undersleeping. Prioritize earlier bedtime for the next 3–5 nights.');
  }
  if ((energy.sleep_consistency_score ?? 100) < 70) {
    items.push('Keep wake time and bedtime more consistent.');
  }
  if (stress > 60) {
    items.push('Use earlier caffeine cutoff and keep the afternoon lighter.');
  }
  return items.length > 0 ? items : ['Normal training and deep work are fine.'];
}

function InfoButton({ title, explanation }: { title: string; explanation?: string }) {
  const [opened, setOpened] = useState(false);
  if (!explanation) return null;

  return (
    <>
      <ActionIcon
        size="sm"
        radius="xl"
        variant="subtle"
        color="gray"
        aria-label={`What is ${title}?`}
        onClick={() => setOpened(true)}
      >
        <IconInfoCircle size={16} stroke={1.8} />
      </ActionIcon>
      <Modal opened={opened} onClose={() => setOpened(false)} title={title} centered>
        <Text size="sm">{explanation}</Text>
        <Text size="xs" c="dimmed" mt="md">These are product estimates for planning, not medical advice.</Text>
      </Modal>
    </>
  );
}

function MetricCard({ label, value, hint, explanation }: { label: string; value: string | number; hint?: string; explanation?: string }) {
  return (
    <Card withBorder radius="lg" p="md" h="100%">
      <Group justify="space-between" align="flex-start" gap="xs">
        <Text size="sm" c="dimmed">{label}</Text>
        <InfoButton title={label} explanation={explanation} />
      </Group>
      <Title order={3}>{value}</Title>
      {hint && <Text size="xs" c="dimmed" mt={4}>{hint}</Text>}
    </Card>
  );
}

function labelColor(label?: string) {
  switch (label) {
    case 'excellent': return 'green';
    case 'good': return 'teal';
    case 'moderate': return 'yellow';
    case 'low': return 'orange';
    case 'poor': return 'red';
    default: return 'gray';
  }
}

const explanations: Record<string, string> = {
  recoveryScore: 'A 0–100 readiness estimate combining sleep pressure, chronic deficit, sleep consistency, stress, resting heart rate, Body Battery, and HRV status when available.',
  decayedSleepDebt: 'Recent sleep loss after applying daily decay. Old debt fades by 10% per day, surplus sleep repays part of it, and the value is capped at 12 hours.',
  sleepPressure: 'A low/moderate/high/very high label based on decayed sleep debt plus chronic nightly deficit.',
  nextDaySleepNeed: 'Estimated sleep target for tonight. It starts from base sleep need, then adjusts for sleep debt repay, chronic deficit repay, nap credit, and recovery penalty.',
  baseSleepNeed: 'Your default baseline sleep need. The current engine uses 8h 15m until user-configurable engine settings are wired in.',
  adjustment: 'The net change from base sleep need: sleep debt repay + chronic deficit repay + recovery penalty - nap credit.',
  wakeSpan: 'Estimated time from wake-up to target bedtime. Base is 17 hours, adjusted earlier when sleep pressure or recovery risk is higher.',
  sleepDebtRepay: 'A recommended extra sleep amount equal to 25% of decayed sleep debt, capped at 90 minutes.',
  chronicDeficitRepay: 'Extra sleep added when your average sleep over recent history is below your base need.',
  napCredit: 'Partial credit from naps. Eligible nap minutes reduce next-day sleep need by 60%, capped at 60 minutes.',
  recoveryPenalty: 'Extra sleep added when recovery score is lower, reflecting higher estimated recovery need.',
  lastNightSleep: 'Total nighttime sleep from Garmin or mock data, excluding nap credit.',
  acuteDebt: 'The sum of positive sleep deficits over the last 14 days, capped at 12 hours. This is shown for context; decayed debt is the main display.',
  chronicDeficit: 'Average nightly shortfall over up to 90 days. This represents persistent under-sleeping rather than accumulated hours.',
  sleepConsistency: 'A 0–100 score based on bedtime and wake-time regularity over the last 14 days.',
  recordedNaps: 'Nap minutes recorded for the day. Garmin may provide aggregate nap minutes or detailed nap rows.',
  bodyBattery: 'Garmin Body Battery estimate at start and end of day, when available. Mock data is used if Garmin data is unavailable.',
  restingHr: 'Resting heart rate from Garmin or mock data. The recovery model can compare this against your recent baseline.',
  stressAvg: 'Average Garmin stress estimate for the day, or mock data if Garmin is unavailable.',
  grogginess: 'Estimated sleep inertia window after wake-up. It lengthens with higher decayed debt or short last-night sleep.',
  morningPeak: 'Estimated first productivity window based on calibrated wake-time phase offsets.',
  afternoonDip: 'Estimated lower-energy afternoon window based on calibrated wake-time phase offsets.',
  eveningPeak: 'Estimated later-day alertness window. Confidence is lower when recovery score is low.',
  windDown: 'Estimated time to start reducing stimulation and preparing for sleep before target bedtime.',
  melatonin: 'Estimated melatonin-friendly sleep timing window around target bedtime. This is not a hormone measurement.',
};

export function TodayDashboard({ today }: Props) {
  const sleep = today.sleep;
  const recovery = today.recovery;
  const energy = today.energy;
  const recoveryScore = Math.max(0, Math.min(100, energy.recovery_score ?? 0));
  const debt = energy.decayed_sleep_debt_minutes ?? energy.sleep_debt_minutes ?? 0;
  const recs = recommendations(today);

  return (
    <Stack gap="md">
      <Alert color="indigo" radius="md" title="Estimated recovery plan">
        Sleep debt is capped and decays over time. Chronic sleep restriction is shown separately as average nightly deficit. {today.disclaimer}
      </Alert>

      <Grid>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card withBorder radius="lg" p="lg" h="100%">
            <Group justify="space-between" align="flex-start">
              <div>
                <Group gap="xs">
                  <Text size="sm" c="dimmed">Recovery Score</Text>
                  <InfoButton title="Recovery Score" explanation={explanations.recoveryScore} />
                </Group>
                <Title order={2}>{recoveryScore}/100</Title>
                <Badge color={labelColor(energy.recovery_label)} mt="xs">{energy.recovery_label ?? 'estimate'}</Badge>
              </div>
              <RingProgress
                size={112}
                thickness={12}
                roundCaps
                sections={[{ value: recoveryScore, color: recoveryScore >= 70 ? 'green' : recoveryScore >= 50 ? 'yellow' : 'red' }]}
                label={<Text ta="center" fw={700}>{recoveryScore}</Text>}
              />
            </Group>
            <Text size="xs" c="dimmed" mt="md">Model: {energy.model_version ?? 'sleep-engine-v2'}. Estimate only.</Text>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <MetricCard label="Decayed sleep debt" value={hours(debt)} hint="Acute debt with daily decay and cap" explanation={explanations.decayedSleepDebt} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card withBorder radius="lg" p="md" h="100%">
            <Group justify="space-between">
              <Group gap="xs">
                <Text size="sm" c="dimmed">Sleep Pressure</Text>
                <InfoButton title="Sleep Pressure" explanation={explanations.sleepPressure} />
              </Group>
              <Badge color={energy.sleep_pressure_label === 'very high' ? 'red' : energy.sleep_pressure_label === 'high' ? 'orange' : energy.sleep_pressure_label === 'moderate' ? 'yellow' : 'green'}>
                {energy.sleep_pressure_label ?? 'low'}
              </Badge>
            </Group>
            <Text size="sm" mt="md">Confidence: {energy.confidence}. Chronic deficit: {energy.chronic_deficit_label ?? 'none'}.</Text>
          </Card>
        </Grid.Col>
      </Grid>

      <Grid>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Next Day Sleep Need" value={hours(energy.next_day_sleep_need_minutes ?? 495)} hint="Dynamic estimate for tonight" explanation={explanations.nextDaySleepNeed} /></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Base Sleep Need" value={hours(energy.base_sleep_need_minutes ?? 495)} hint="Default baseline" explanation={explanations.baseSleepNeed} /></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Adjustment" value={`${(energy.sleep_need_adjustment_minutes ?? 0) >= 0 ? '+' : ''}${energy.sleep_need_adjustment_minutes ?? 0} min`} hint="Debt + chronic + recovery - naps" explanation={explanations.adjustment} /></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Wake span" value={hours(energy.dynamic_wake_span_minutes ?? 1020)} hint="Wake to target bedtime" explanation={explanations.wakeSpan} /></Grid.Col>
      </Grid>

      <Grid>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Sleep Debt Repay" value={hours(energy.acute_debt_repay_minutes ?? 0)} hint="25% of decayed debt, capped" explanation={explanations.sleepDebtRepay} /></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Chronic Deficit Repay" value={hours(energy.chronic_deficit_repay_minutes ?? 0)} hint="Extra sleep for persistent deficit" explanation={explanations.chronicDeficitRepay} /></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Nap Credit" value={`-${hours(energy.nap_credit_minutes ?? 0)}`} hint={(today.naps?.length ?? 0) > 0 ? `${sleep.nap_minutes ?? 0} nap min recorded` : 'No naps recorded'} explanation={explanations.napCredit} /></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Recovery Penalty" value={hours(energy.recovery_penalty_minutes ?? 0)} hint="Added when recovery is lower" explanation={explanations.recoveryPenalty} /></Grid.Col>
      </Grid>

      <Grid>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Last night sleep" value={hours(sleep.total_sleep_minutes)} hint={range(sleep.sleep_start, sleep.sleep_end)} explanation={explanations.lastNightSleep} /></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Acute debt" value={hours(energy.acute_sleep_debt_minutes ?? 0)} hint="14-day positive deficit, capped" explanation={explanations.acuteDebt} /></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Chronic deficit" value={`${energy.chronic_sleep_deficit_minutes_per_night ?? 0} min/night`} hint="Average nightly shortfall" explanation={explanations.chronicDeficit} /></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Sleep consistency" value={`${energy.sleep_consistency_score ?? 100}/100`} hint="Bedtime + wake-time regularity" explanation={explanations.sleepConsistency} /></Grid.Col>
      </Grid>

      <Grid>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Recorded naps" value={hours(sleep.nap_minutes ?? 0)} hint={(today.naps?.length ?? 0) > 0 ? `${today.naps?.length} nap row(s)` : 'No naps recorded'} explanation={explanations.recordedNaps} /></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Body Battery" value={`${recovery.body_battery_start} → ${recovery.body_battery_end}`} explanation={explanations.bodyBattery} /></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Resting HR" value={`${recovery.resting_hr} bpm`} explanation={explanations.restingHr} /></Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}><MetricCard label="Stress avg" value={recovery.stress_avg} explanation={explanations.stressAvg} /></Grid.Col>
      </Grid>

      <Card withBorder radius="lg" p="lg">
        <Title order={3} mb="sm">Today’s estimated energy windows</Title>
        <Grid>
          <Grid.Col span={{ base: 12, md: 6 }}><MetricCard label="Grogginess" value={range(energy.grogginess_start, energy.grogginess_end)} explanation={explanations.grogginess} /></Grid.Col>
          <Grid.Col span={{ base: 12, md: 6 }}><MetricCard label="Morning productivity peak" value={range(energy.morning_peak_start, energy.morning_peak_end)} explanation={explanations.morningPeak} /></Grid.Col>
          <Grid.Col span={{ base: 12, md: 6 }}><MetricCard label="Afternoon dip" value={range(energy.afternoon_dip_start, energy.afternoon_dip_end)} explanation={explanations.afternoonDip} /></Grid.Col>
          <Grid.Col span={{ base: 12, md: 6 }}><MetricCard label="Evening peak" value={range(energy.evening_peak_start, energy.evening_peak_end)} hint={energy.recovery_score < 50 ? 'Lower confidence today' : undefined} explanation={explanations.eveningPeak} /></Grid.Col>
          <Grid.Col span={{ base: 12, md: 6 }}><MetricCard label="Wind-down" value={range(energy.wind_down_start, energy.target_bedtime)} explanation={explanations.windDown} /></Grid.Col>
          <Grid.Col span={{ base: 12, md: 6 }}><MetricCard label="Estimated melatonin window" value={range(energy.melatonin_window_start, energy.melatonin_window_end)} explanation={explanations.melatonin} /></Grid.Col>
        </Grid>
      </Card>

      <Card withBorder radius="lg" p="lg">
        <Group justify="space-between" mb="xs">
          <Title order={3}>Recommendations</Title>
          <Badge variant="light">estimate</Badge>
        </Group>
        <List spacing="xs">
          {recs.map((item) => <List.Item key={item}>{item}</List.Item>)}
        </List>
        <Progress mt="md" value={recoveryScore} color={recoveryScore >= 70 ? 'green' : recoveryScore >= 50 ? 'yellow' : 'red'} />
      </Card>

      <Card withBorder radius="lg" p="lg">
        <Title order={3} mb="sm">How this is calculated</Title>
        <List spacing="xs" size="sm">
          <List.Item>Sleep need is dynamic. It starts from your base need, then adjusts for recent sleep debt, chronic deficit, naps, and recovery signals.</List.Item>
          <List.Item>Energy windows use calibrated wake-time offsets and a dynamic wake span, not the old fixed 16-hour bedtime.</List.Item>
          <List.Item>Acute debt = recent sleep loss with a 12-hour cap and daily decay.</List.Item>
          <List.Item>All predictions are estimates for planning, not medical diagnosis.</List.Item>
        </List>
      </Card>
    </Stack>
  );
}
