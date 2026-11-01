import { Stack } from 'expo-router';
import { useEffect } from 'react';
import { appFacade } from '@/application/appFacade';

export default function RootLayout() {
  useEffect(() => {
    appFacade.init().catch((error) => {
      console.error('init error', error);
    });

    return () => {
      appFacade.shutdown();
    };
  }, []);

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="judge-setup" />
      <Stack.Screen name="connection" />
      <Stack.Screen name="match-setup" />
      <Stack.Screen name="technical-scoring" />
      <Stack.Screen name="presentation" />
      <Stack.Screen name="summary" />
      <Stack.Screen name="history" />
      <Stack.Screen name="settings" />
    </Stack>
  );
}
