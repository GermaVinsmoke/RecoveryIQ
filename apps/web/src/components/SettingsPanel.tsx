import { Alert, Card, Code, List, NumberInput, Stack, Text, TextInput, Title } from '@mantine/core';
import { useLocalStorage } from '@mantine/hooks';

export function SettingsPanel() {
  const [sleepNeed, setSleepNeed] = useLocalStorage({ key: 'recoveryiq.sleepNeedMinutes', defaultValue: 495 });
  const [wakeTime, setWakeTime] = useLocalStorage({ key: 'recoveryiq.defaultWakeTime', defaultValue: '07:00' });

  return (
    <Stack gap="md">
      <Alert color="yellow" title="Local MVP settings">
        These preferences are saved in this browser. The current sync engine uses the MVP default sleep need of 8h 15m unless you edit the script.
      </Alert>
      <Card withBorder radius="lg" p="lg">
        <Title order={3} mb="md">Planning preferences</Title>
        <Stack maw={420}>
          <NumberInput label="Sleep need minutes" value={sleepNeed} onChange={(v) => setSleepNeed(Number(v) || 495)} min={300} max={720} />
          <TextInput label="Default wake time" type="time" value={wakeTime} onChange={(e) => setWakeTime(e.currentTarget.value)} />
        </Stack>
      </Card>
      <Card withBorder radius="lg" p="lg">
        <Title order={3} mb="sm">Garmin environment setup</Title>
        <Text size="sm" c="dimmed" mb="md">Garmin Connect access is unofficial and may break. If login fails or credentials are absent, Recovery IQ automatically uses mock data.</Text>
        <List spacing="xs">
          <List.Item>Install Python dependencies with <Code>make setup</Code>.</List.Item>
          <List.Item>Set <Code>GARMIN_EMAIL</Code> and <Code>GARMIN_PASSWORD</Code> in your shell.</List.Item>
          <List.Item>Run <Code>make sync</Code> or press the Sync button in the app.</List.Item>
        </List>
      </Card>
    </Stack>
  );
}
