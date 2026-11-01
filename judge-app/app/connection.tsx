import { useFocusEffect, useLocalSearchParams, router } from 'expo-router';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useCallback, useMemo, useState } from 'react';
import { Ionicons } from '@expo/vector-icons';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Modal, Platform, StyleSheet, Text, TextInput, View } from 'react-native';
import { appFacade } from '@/application/appFacade';
import { PrimaryButton } from '@/components/PrimaryButton';
import { ScreenContainer } from '@/components/ScreenContainer';
import { StatusBadge } from '@/components/StatusBadge';
import { Colors } from '@/constants/colors';
import { DEFAULT_STATION_ID } from '@/constants/defaults';
import { t } from '@/i18n';
import { errorMessage } from '@/i18n/LocalizedError';

export default function ConnectionScreen() {
  const params = useLocalSearchParams<{ returnTo?: string }>();
  const [settingsJudgeName, setSettingsJudgeName] = useState('');
  const [judgeName, setJudgeName] = useState('');
  const [selectedStationId, setSelectedStationId] = useState(DEFAULT_STATION_ID);
  const [credential, setCredential] = useState('');
  const [rawQr, setRawQr] = useState('');
  const [busy, setBusy] = useState(false);
  const [connectedToServer, setConnectedToServer] = useState(false);
  const [scannerOpen, setScannerOpen] = useState(false);
  const [showCredentialPrompt, setShowCredentialPrompt] = useState(false);
  const [permission, requestPermission] = useCameraPermissions();

  const backendBadgeTone = useMemo(() => (connectedToServer ? 'ok' : 'warn'), [connectedToServer]);
  const backendLabel = connectedToServer ? t('status.connected') : t('status.notConnected');
  const resolveReturnPath = (hasActiveMatch: boolean) => {
    if (params.returnTo === 'presentation') return '/presentation';
    if (params.returnTo === 'match-setup') return '/match-setup';
    if (hasActiveMatch) return '/technical-scoring';
    return '/match-setup';
  };

  const load = useCallback(async () => {
    const [settings, connection] = await Promise.all([appFacade.getSettings(), appFacade.getConnectionInfo()]);
    setSettingsJudgeName(settings.judgeName);
    setJudgeName(settings.judgeName);
    setSelectedStationId(connection.session?.stationId || settings.defaultStationId || DEFAULT_STATION_ID);
    setConnectedToServer(Boolean(connection.session && connection.session.stationId !== 'local-offline' && connection.session.connectionStatus === 'connected'));
  }, []);

  useFocusEffect(
    useCallback(() => {
      load().catch(() => undefined);
      return undefined;
    }, [load])
  );

  const applyQrPayload = async (payload: string) => {
    setBusy(true);
    try {
      const qr = await appFacade.saveQr(payload);
      setSelectedStationId(qr.stationId);
      const stations = await appFacade.refreshStations().catch(() => []);
      if (stations.length > 0) {
        const stillExists = stations.some((s) => s.id === qr.stationId);
        if (!stillExists) {
          Alert.alert(t('connection.warningTitle'), t('connection.qrStationNotActive', { stationId: qr.stationId }));
        }
      }
      setScannerOpen(false);
      setShowCredentialPrompt(true);
    } catch (error: any) {
      Alert.alert(t('connection.invalidQrTitle'), errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const onConnect = async (): Promise<boolean> => {
    if (!selectedStationId || !credential) {
      Alert.alert(t('connection.missingDataTitle'), t('connection.missingDataMessage'));
      return false;
    }

    setBusy(true);
    try {
      await appFacade.connectStation({
        stationId: selectedStationId,
        credential: credential.trim(),
        judgeName: judgeName.trim() || settingsJudgeName
      });
      setConnectedToServer(true);
      const active = await appFacade.getActiveScoring();
      router.replace(resolveReturnPath(Boolean(active?.match)));
      return true;
    } catch (error: any) {
      Alert.alert(t('connection.signInFailedTitle'), errorMessage(error));
      return false;
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScreenContainer keyboardAware>
      <View style={styles.headerRow}>
        <Text style={styles.title}>{t('connection.title')}</Text>
        <StatusBadge label={backendLabel} tone={backendBadgeTone} />
      </View>
      <PrimaryButton
        testID="connection-back-btn"
        title=""
        icon={<Ionicons name="arrow-back" size={24} color="#fff" />}
        variant="gray"
        size="compact"
        onPress={() => router.replace('/match-setup')}
      />

      <TextInput
        testID="judge-input"
        style={styles.input}
        value={judgeName}
        onChangeText={setJudgeName}
        placeholder={t('connection.judgePlaceholder')}
      />

      <View style={styles.block}>
        <Text style={styles.blockTitle}>{t('connection.qrCode')}</Text>
        <PrimaryButton
          testID="scan-qr-btn"
          title={t('connection.scanQr')}
          onPress={async () => {
            if (!permission?.granted) {
              await requestPermission();
            }
            setScannerOpen(true);
          }}
        />
        {scannerOpen ? (
          <PrimaryButton
            testID="close-camera-btn"
            title={t('connection.closeCamera')}
            variant="gray" size="compact" onPress={() => setScannerOpen(false)} />
        ) : null}

        {scannerOpen ? (
          <View style={styles.cameraBox}>
            {!permission?.granted ? (
              <Text style={styles.note}>{t('connection.cameraPermissionRequired')}</Text>
            ) : (
              <CameraView
                style={StyleSheet.absoluteFill}
                barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
                onBarcodeScanned={(event) => {
                  if (busy) return;
                  applyQrPayload(event.data);
                }}
              />
            )}
          </View>
        ) : null}

        <TextInput
          testID="qr-paste-input"
          style={styles.inputSmall}
          value={rawQr}
          onChangeText={setRawQr}
          placeholder={t('connection.pasteQrPlaceholder')}
          multiline
        />
        <PrimaryButton
          testID="use-pasted-qr-btn"
          title={t('connection.usePastedQr')}
          variant="gray"
          disabled={!rawQr || busy}
          onPress={() => applyQrPayload(rawQr)}
        />
      </View>

      <TextInput
        testID="credential-input"
        style={styles.input}
        value={credential}
        onChangeText={setCredential}
        placeholder={t('connection.credentialPlaceholder')}
        autoCapitalize="none"
      />

      <PrimaryButton testID="connect-btn" title={busy ? t('connection.signingIn') : t('connection.signIn')} onPress={onConnect} disabled={busy} />

      {connectedToServer ? (
        <PrimaryButton
          testID="disconnect-btn"
          title={t('connection.disconnect')}
          variant="red"
          onPress={() => {
            Alert.alert(t('connection.disconnect'), t('connection.disconnectMessage'), [
              { text: t('common.cancel'), style: 'cancel' },
              {
                text: t('connection.disconnectConfirm'),
                style: 'destructive',
                onPress: () => {
                  appFacade
                    .disconnectServerSession()
                    .then(() => {
                      setConnectedToServer(false);
                      setCredential('');
                      setShowCredentialPrompt(false);
                    })
                    .catch((error: any) => {
                      Alert.alert(t('common.error'), errorMessage(error));
                    });
                }
              }
            ]);
          }}
        />
      ) : null}

      {busy ? <ActivityIndicator color={Colors.navy} size="large" /> : null}

      <Modal visible={showCredentialPrompt} transparent animationType="fade" onRequestClose={() => setShowCredentialPrompt(false)}>
        <KeyboardAvoidingView style={styles.modalBackdrop} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>{t('connection.stationPasswordTitle')}</Text>
            <Text style={styles.modalSub}>{selectedStationId || DEFAULT_STATION_ID}</Text>
            <TextInput
              testID="credential-prompt-input"
              style={styles.modalInput}
              value={credential}
              onChangeText={setCredential}
              placeholder={t('connection.credentialPlaceholder')}
              autoCapitalize="none"
            />
            <View style={styles.modalActions}>
              <PrimaryButton
                testID="credential-prompt-cancel-btn"
                title={t('common.cancel')}
                variant="gray"
                size="compact"
                onPress={() => setShowCredentialPrompt(false)}
              />
              <PrimaryButton
                testID="credential-prompt-connect-btn"
                title={busy ? t('connection.connecting') : t('connection.signIn')}
                variant="blue"
                size="compact"
                disabled={busy}
                onPress={() => {
                  onConnect()
                    .then((ok) => {
                      if (ok) {
                        setShowCredentialPrompt(false);
                      }
                    })
                    .catch(() => undefined);
                }}
              />
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  title: {
    fontSize: 42,
    fontWeight: '900',
    color: Colors.navy
  },
  block: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 12,
    gap: 8
  },
  blockTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: Colors.navy
  },
  input: {
    minHeight: 68,
    borderRadius: 14,
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    fontSize: 24,
    fontWeight: '700'
  },
  inputSmall: {
    minHeight: 56,
    borderRadius: 12,
    backgroundColor: '#F8FAFC',
    paddingHorizontal: 14,
    fontSize: 16,
    borderWidth: 1,
    borderColor: '#CBD5E1'
  },
  cameraBox: {
    height: 220,
    borderRadius: 14,
    overflow: 'hidden',
    backgroundColor: '#0b1220'
  },
  note: {
    color: '#fff',
    fontWeight: '700',
    textAlign: 'center',
    marginTop: 100
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(2,6,23,0.58)',
    justifyContent: 'center',
    padding: 20
  },
  modalCard: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 14,
    gap: 10
  },
  modalTitle: {
    fontSize: 26,
    fontWeight: '900',
    color: Colors.navy
  },
  modalSub: {
    fontSize: 14,
    fontWeight: '700',
    color: Colors.subtle
  },
  modalInput: {
    minHeight: 60,
    borderRadius: 12,
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: '#CBD5E1',
    paddingHorizontal: 14,
    fontSize: 22,
    fontWeight: '700'
  },
  modalActions: {
    flexDirection: 'row',
    gap: 8
  }
});
