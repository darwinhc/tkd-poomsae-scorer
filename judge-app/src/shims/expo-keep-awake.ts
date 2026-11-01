export const ExpoKeepAwakeTag = 'ExpoKeepAwakeDefaultTag';

export function useKeepAwake(): void {
  // No-op shim for dev environments where native keep-awake may fail.
}

export async function activateKeepAwakeAsync(): Promise<void> {
  // No-op
}

export async function deactivateKeepAwake(): Promise<void> {
  // No-op
}

export async function isAvailableAsync(): Promise<boolean> {
  return false;
}
