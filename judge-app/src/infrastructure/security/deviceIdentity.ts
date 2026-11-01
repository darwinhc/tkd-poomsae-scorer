import AsyncStorage from '@react-native-async-storage/async-storage';
import { createId } from '@/utils/id';

const DEVICE_ID_KEY = 'tkd.device_id';

export async function getOrCreateDeviceId(): Promise<string> {
  const existing = await AsyncStorage.getItem(DEVICE_ID_KEY);
  if (existing) {
    return existing;
  }

  const created = `dev-${createId()}`;
  await AsyncStorage.setItem(DEVICE_ID_KEY, created);
  return created;
}
