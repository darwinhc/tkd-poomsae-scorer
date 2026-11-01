import NetInfo from '@react-native-community/netinfo';
import { AppState, type AppStateStatus } from 'react-native';

export interface ConnectivityCallbacks {
  onOnline?: () => void;
  onResume?: () => void;
}

export function startConnectivityMonitor(callbacks: ConnectivityCallbacks) {
  const unsubNet = NetInfo.addEventListener((state) => {
    if (state.isConnected) {
      callbacks.onOnline?.();
    }
  });

  const sub = AppState.addEventListener('change', (status: AppStateStatus) => {
    if (status === 'active') {
      callbacks.onResume?.();
    }
  });

  return () => {
    unsubNet();
    sub.remove();
  };
}
