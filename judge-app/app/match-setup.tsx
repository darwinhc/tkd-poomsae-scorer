import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Ionicons } from '@expo/vector-icons';
import { Alert, StyleSheet, Text, TextInput, View } from 'react-native';
import { appFacade } from '@/application/appFacade';
import { PrimaryButton } from '@/components/PrimaryButton';
import { ScreenContainer } from '@/components/ScreenContainer';
import { StatusBadge } from '@/components/StatusBadge';
import { Colors } from '@/constants/colors';
import { useAppStore } from '@/store/appStore';
import { t } from '@/i18n';
import { errorMessage } from '@/i18n/LocalizedError';

export default function MatchSetupScreen() {
  const wsStatus = useAppStore((s) => s.wsStatus);
  const settingsVersion = useAppStore((s) => s.settingsVersion);
  const [redName, setRedName] = useState(() => t('common.red'));
  const [blueName, setBlueName] = useState(() => t('common.blue'));
  const [redOnLeft, setRedOnLeft] = useState(true);
  const [serverHasActiveMatch, setServerHasActiveMatch] = useState(false);
  const [serverActiveMatchId, setServerActiveMatchId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const isConnected = wsStatus === 'connected';
  const connectionLabel =
    wsStatus === 'connected' ? t('status.connected') : wsStatus === 'connecting' ? t('status.reconnecting') : t('status.notConnected');
  const connectionTone = wsStatus === 'connected' ? 'ok' : wsStatus === 'connecting' ? 'neutral' : 'warn';
  const connectionIconName = wsStatus === 'connected' ? 'wifi' : wsStatus === 'connecting' ? 'sync' : 'cloud-offline-outline';

  const loadPersistedSide = useCallback(async () => {
    const [settings, connection] = await Promise.all([appFacade.getSettings(), appFacade.getConnectionInfo()]);
    const redOnLeftNext = (settings.preferredRedSide ?? 'LEFT') === 'LEFT';
    setRedOnLeft(redOnLeftNext);
    setServerHasActiveMatch(false);
    setServerActiveMatchId(null);
    if (settings.serverCompetitorRedName?.trim() && settings.serverCompetitorBlueName?.trim()) {
      setRedName(settings.serverCompetitorRedName.trim());
      setBlueName(settings.serverCompetitorBlueName.trim());
    }
    if (!connection.session) {
      await appFacade.connectLocalMode(settings.judgeName);
    }

    if (connection.session && connection.session.stationId !== 'local-offline') {
      const snapshot = await appFacade.refreshActiveMatchSnapshot().catch(() => ({ hasActiveMatch: false } as const));
      setServerHasActiveMatch(Boolean(snapshot?.hasActiveMatch));
      setServerActiveMatchId(snapshot?.hasActiveMatch ? snapshot.matchId ?? null : null);
      if (snapshot?.hasActiveMatch) {
        setRedName(snapshot.redName?.trim() || t('common.red'));
        setBlueName(snapshot.blueName?.trim() || t('common.blue'));
      }
    }
  }, [wsStatus]);

  useFocusEffect(
    useCallback(() => {
      loadPersistedSide().catch(() => undefined);
      return undefined;
    }, [loadPersistedSide, settingsVersion])
  );

  const swapSides = () => {
    setRedOnLeft((prev) => {
      const next = !prev;
      appFacade.savePreferredRedSide(next ? 'LEFT' : 'RIGHT').catch(() => undefined);
      return next;
    });
  };

  const onCreate = async () => {
    if (!redName || !blueName) {
      Alert.alert(t('matchSetup.missingNames'));
      return;
    }

    setLoading(true);
    try {
      const competitorLeftName = redOnLeft ? redName.trim() : blueName.trim();
      const competitorRightName = redOnLeft ? blueName.trim() : redName.trim();
      await appFacade.savePreferredRedSide(redOnLeft ? 'LEFT' : 'RIGHT');
      await appFacade.createMatch({
        competitorLeftName,
        competitorRightName,
        leftSideColor: redOnLeft ? 'RED' : 'BLUE',
        rightSideColor: redOnLeft ? 'BLUE' : 'RED'
      });
      router.replace('/technical-scoring');
    } catch (error: any) {
      Alert.alert(t('common.error'), errorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const onSync = async () => {
    setSyncing(true);
    try {
      await appFacade.resyncNow();
      await loadPersistedSide();
    } catch (error: any) {
      Alert.alert(t('matchSetup.syncErrorTitle'), errorMessage(error));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <ScreenContainer>
      <View style={styles.headerRow}>
        <Text style={styles.title}>{t('matchSetup.title')}</Text>
        <StatusBadge
          testID="connection-badge"
          label={connectionLabel}
          tone={connectionTone}
          icon={<Ionicons name={connectionIconName} size={14} color="#fff" />}
          onPress={() => router.push({ pathname: '/connection', params: { returnTo: 'match-setup' } })}
        />
      </View>
      {isConnected ? (
        <StatusBadge
          testID="active-match-badge"
          label={
            serverHasActiveMatch
              ? serverActiveMatchId
                ? t('matchSetup.activeMatchWithId', { matchId: serverActiveMatchId })
                : t('matchSetup.activeMatch')
              : t('matchSetup.noActiveMatch')
          }
          tone={serverHasActiveMatch ? 'ok' : 'neutral'}
          icon={<Ionicons name={serverHasActiveMatch ? 'trophy' : 'ellipse-outline'} size={14} color="#fff" />}
        />
      ) : null}

      {isConnected ? (
        <PrimaryButton
          testID="sync-match-btn"
          title={syncing ? t('matchSetup.syncing') : t('matchSetup.sync')}
          variant="gray"
          size="compact"
          icon={<Ionicons name="sync" size={20} color="#fff" />}
          onPress={() => {
            onSync().catch(() => undefined);
          }}
          disabled={syncing}
        />
      ) : null}

      <PrimaryButton
        testID="swap-sides-btn"
        title={t('matchSetup.swapSides')}
        variant="gray"
        size="compact"
        icon={<Ionicons name="swap-horizontal" size={22} color="#fff" />}
        onPress={swapSides}
      />

      <View style={styles.sideBoxRed}>
        <Text style={styles.sideLabel}>{t('matchSetup.redSideLabel', { side: redOnLeft ? t('common.left') : t('common.right') })}</Text>
        <TextInput
          testID="red-name-input"
          style={styles.input}
          value={redName}
          onChangeText={setRedName}
        />
      </View>

      <View style={styles.sideBoxBlue}>
        <Text style={styles.sideLabel}>{t('matchSetup.blueSideLabel', { side: redOnLeft ? t('common.right') : t('common.left') })}</Text>
        <TextInput
          testID="blue-name-input"
          style={styles.input}
          value={blueName}
          onChangeText={setBlueName}
        />
      </View>

      <Text style={styles.note}>{t('matchSetup.note')}</Text>

      <PrimaryButton testID="open-settings-btn" title={t('matchSetup.settings')} size="compact" onPress={() => router.push('/settings')} />
      <PrimaryButton testID="start-match-btn" variant="blue" title={loading ? t('matchSetup.starting') : t('matchSetup.start')} onPress={onCreate} disabled={loading} />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between'
  },
  title: {
    fontSize: 42,
    fontWeight: '900',
    color: Colors.navy
  },
  sideBoxRed: {
    backgroundColor: '#FDECEC',
    borderRadius: 14,
    padding: 10,
    borderWidth: 2,
    borderColor: Colors.red
  },
  sideBoxBlue: {
    backgroundColor: '#EAF2FF',
    borderRadius: 14,
    padding: 10,
    borderWidth: 2,
    borderColor: Colors.blue
  },
  sideLabel: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.navy,
    marginBottom: 8
  },
  input: {
    minHeight: 64,
    borderRadius: 12,
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    fontSize: 24,
    fontWeight: '700'
  },
  note: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.navy,
    opacity: 0.75
  }
});
