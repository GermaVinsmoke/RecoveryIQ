import { useEffect, useState } from 'react';
import { Alert, AppShell, Badge, Button, Group, Loader, Stack, Tabs, Text, Title } from '@mantine/core';
import { api } from './api';
import type { DailyRecovery, DailySleep, EnergyWindows, TodayResponse } from './types';
import { TodayDashboard } from './components/TodayDashboard';
import { SleepTrend } from './components/SleepTrend';
import { RecoveryCards } from './components/RecoveryCards';
import { EnergyTimeline } from './components/EnergyTimeline';
import { SettingsPanel } from './components/SettingsPanel';

export default function App() {
  const [today, setToday] = useState<TodayResponse | null>(null);
  const [sleep, setSleep] = useState<DailySleep[]>([]);
  const [recovery, setRecovery] = useState<DailyRecovery[]>([]);
  const [energy, setEnergy] = useState<EnergyWindows[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncOutput, setSyncOutput] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [todayRes, sleepRes, recoveryRes, energyRes] = await Promise.all([
        api.today(),
        api.sleep(30),
        api.recovery(30),
        api.energy(14),
      ]);
      setToday(todayRes);
      setSleep(sleepRes);
      setRecovery(recoveryRes);
      setEnergy(energyRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Recovery IQ data');
    } finally {
      setLoading(false);
    }
  }

  async function runSync() {
    setSyncing(true);
    setError(null);
    setSyncOutput(null);
    try {
      const res = await api.sync(30);
      setSyncOutput(res.output.trim());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <AppShell header={{ height: 68 }} padding="md">
      <AppShell.Header px="md">
        <Group h="100%" justify="space-between">
          <Group gap="sm">
            <Title order={2}>Recovery IQ</Title>
            <Badge variant="light">local only</Badge>
          </Group>
          <Group>
            <Text size="sm" c="dimmed" visibleFrom="sm">Garmin-inspired sleep and recovery estimates</Text>
            <Button onClick={runSync} loading={syncing}>Sync</Button>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Stack gap="md">
          {error && (
            <Alert color="red" title="Data unavailable">
              {error}
              <Text size="sm" mt="xs">Try running <code>make sync</code> from the project root, or press Sync to seed mock data.</Text>
            </Alert>
          )}
          {syncOutput && <Alert color="green" title="Sync complete"><pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{syncOutput}</pre></Alert>}

          {loading ? (
            <Group justify="center" mt="xl"><Loader /></Group>
          ) : today ? (
            <Tabs defaultValue="today" keepMounted={false}>
              <Tabs.List>
                <Tabs.Tab value="today">Today</Tabs.Tab>
                <Tabs.Tab value="sleep">Sleep trend</Tabs.Tab>
                <Tabs.Tab value="recovery">Recovery</Tabs.Tab>
                <Tabs.Tab value="energy">Energy timeline</Tabs.Tab>
                <Tabs.Tab value="settings">Settings</Tabs.Tab>
              </Tabs.List>

              <Tabs.Panel value="today" pt="md"><TodayDashboard today={today} /></Tabs.Panel>
              <Tabs.Panel value="sleep" pt="md"><SleepTrend rows={sleep} /></Tabs.Panel>
              <Tabs.Panel value="recovery" pt="md"><RecoveryCards rows={recovery} /></Tabs.Panel>
              <Tabs.Panel value="energy" pt="md"><EnergyTimeline rows={energy} /></Tabs.Panel>
              <Tabs.Panel value="settings" pt="md"><SettingsPanel /></Tabs.Panel>
            </Tabs>
          ) : (
            <Alert color="blue" title="No data yet">
              Press Sync or run <code>make sync</code>. The app will create mock data if Garmin credentials are not configured.
            </Alert>
          )}
        </Stack>
      </AppShell.Main>
    </AppShell>
  );
}
