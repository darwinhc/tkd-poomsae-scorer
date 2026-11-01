import * as SecureStore from 'expo-secure-store';

const ACCESS_TOKEN_KEY = 'tkd.access_token';

export const tokenVault = {
  async save(accessToken: string) {
    await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, accessToken);
  },
  async load() {
    return SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
  },
  async clear() {
    await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
  }
};
