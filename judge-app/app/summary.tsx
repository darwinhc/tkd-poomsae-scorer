import { useFocusEffect, useLocalSearchParams, router } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';
import { appFacade } from '@/application/appFacade';
import { PrimaryButton } from '@/components/PrimaryButton';
import { ScreenContainer } from '@/components/ScreenContainer';
import { Colors } from '@/constants/colors';
import { useAppStore } from '@/store/appStore';
import { t } from '@/i18n';

export default function SummaryScreen() {
  const wsStatus = useAppStore((s) => s.wsStatus);
  const params = useLocalSearchParams<{ matchId?: string }>();
  const [summary, setSummary] = useState<any>(null);
  const [connection, setConnection] = useState<any>(null);

  const load = useCallback(async () => {
    let matchId = params.matchId;
    if (!matchId) {
      const active = await appFacade.getActiveScoring();
      matchId = active?.match.id;
    }

    if (!matchId) {
      setSummary(null);
      return;
    }

    const [s, c] = await Promise.all([appFacade.getSummary(matchId), appFacade.getConnectionInfo()]);
    setSummary(s);
    setConnection(c);
  }, [params.matchId]);

  useFocusEffect(
    useCallback(() => {
      load().catch(() => undefined);
      return undefined;
    }, [load])
  );

  const roundsWithTotal = useMemo(() => {
    if (!summary?.rounds) return [];
    return summary.rounds.map((round: any) => ({
      ...round,
      total: {
        red: round1(round.technique.red + round.presentationTotal.red),
        blue: round1(round.technique.blue + round.presentationTotal.blue)
      }
    }));
  }, [summary?.rounds]);

  const waitingServer = useMemo(() => {
    if (!connection?.session) return false;
    const remoteSession = connection.session.stationId !== 'local-offline';
    return remoteSession && wsStatus === 'connected';
  }, [connection?.session, wsStatus]);

  const overallTotal = useMemo(() => {
    if (!summary) return null;
    return {
      red: round2(summary.technique.red + summary.presentationTotal.red),
      blue: round2(summary.technique.blue + summary.presentationTotal.blue)
    };
  }, [summary]);

  const stationLabel = !connection?.session
    ? t('summary.noStation')
    : connection.session.stationId === 'local-offline'
      ? t('common.localMode')
      : connection.session.stationName ?? t('summary.noStation');

  if (!summary) {
    return (
      <ScreenContainer>
        <Text testID="summary-title" style={styles.title}>
          {t('summary.title')}
        </Text>
        <Text style={styles.small}>{t('summary.noData')}</Text>
        <PrimaryButton title={t('summary.goToScoring')} onPress={() => router.replace('/technical-scoring')} />
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer contentStyle={styles.container}>
      <View style={styles.header}>
        <Text testID="summary-title" style={styles.title}>
          {t('summary.title')}
        </Text>
        <Text style={styles.headerStatus}>{friendlyMatchStatus(summary.finalizationStatus)}</Text>
      </View>
      {overallTotal ? (
        <View style={styles.overallRow}>
          <View style={[styles.overallBadge, styles.overallBadgeRed]}>
            <Text style={styles.overallText}>{t('summary.redTotal', { total: formatTotal(overallTotal.red) })}</Text>
          </View>
          <View style={[styles.overallBadge, styles.overallBadgeBlue]}>
            <Text style={styles.overallText}>{t('summary.blueTotal', { total: formatTotal(overallTotal.blue) })}</Text>
          </View>
        </View>
      ) : null}

      <View style={styles.sectionCard}>
        <Text style={styles.sectionTitle}>{t('summary.rounds')}</Text>
        {roundsWithTotal.map((round: any) => (
          <View key={round.roundNumber} style={styles.roundCard}>
            <Text style={styles.roundTitle}>{t('summary.roundTitle', { number: round.roundNumber })}</Text>

            <View style={[styles.competitorSection, styles.competitorSectionRed]}>
              <Text style={[styles.sideLabel, styles.sideLabelRed]}>{t('common.redUpper')}</Text>
              <View style={styles.indicatorsRow}>
                <View style={styles.indicatorPill}>
                  <Text style={styles.indicatorLabel}>{t('common.technique')}</Text>
                  <Text style={styles.indicatorValue}>{round.technique.red.toFixed(1)}</Text>
                </View>
                <View style={styles.indicatorPill}>
                  <Text style={styles.indicatorLabel}>{t('common.presentation')}</Text>
                  <Text style={styles.indicatorValue}>{round.presentationTotal.red.toFixed(1)}</Text>
                </View>
                <View style={[styles.indicatorPill, styles.indicatorTotalPill]}>
                  <Text style={styles.indicatorLabel}>{t('common.total')}</Text>
                  <Text style={styles.indicatorValue}>{formatTotal(round.total.red)}</Text>
                </View>
              </View>
            </View>

            <View style={[styles.competitorSection, styles.competitorSectionBlue]}>
              <Text style={[styles.sideLabel, styles.sideLabelBlue]}>{t('common.blueUpper')}</Text>
              <View style={styles.indicatorsRow}>
                <View style={styles.indicatorPill}>
                  <Text style={styles.indicatorLabel}>{t('common.technique')}</Text>
                  <Text style={styles.indicatorValue}>{round.technique.blue.toFixed(1)}</Text>
                </View>
                <View style={styles.indicatorPill}>
                  <Text style={styles.indicatorLabel}>{t('common.presentation')}</Text>
                  <Text style={styles.indicatorValue}>{round.presentationTotal.blue.toFixed(1)}</Text>
                </View>
                <View style={[styles.indicatorPill, styles.indicatorTotalPill]}>
                  <Text style={styles.indicatorLabel}>{t('common.total')}</Text>
                  <Text style={styles.indicatorValue}>{formatTotal(round.total.blue)}</Text>
                </View>
              </View>
            </View>
          </View>
        ))}
      </View>

      <View style={styles.metaRow}>
        <Text style={styles.small}>{t('summary.station', { name: stationLabel })}</Text>
        <Text style={styles.small}>{t('summary.server', { status: connection?.backend?.baseUrl ? t('status.connected') : t('status.notConnected') })}</Text>
      </View>

      <View style={styles.buttons}>
        {waitingServer ? (
          <View style={styles.waitBox}>
            <Text style={styles.waitTitle}>{t('summary.waitingNewMatch')}</Text>
          </View>
        ) : (
          <PrimaryButton testID="restart-btn" title={t('summary.restart')} variant="green" onPress={() => router.replace('/match-setup')} />
        )}
        <PrimaryButton
          testID="send-now-btn"
          title={t('summary.sendNow')}
          variant="gray"
          onPress={() => {
            appFacade
              .syncNow()
              .then(() => Alert.alert(t('summary.syncStarted')))
              .catch(() => Alert.alert(t('summary.syncFailed')));
          }}
        />
        <PrimaryButton testID="history-btn" title={t('summary.history')} variant="blue" onPress={() => router.push('/history')} />
        <PrimaryButton testID="summary-back-btn" title={t('common.back')} variant="gray" onPress={() => router.back()} />
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 10
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between'
  },
  title: {
    fontSize: 34,
    fontWeight: '900',
    color: Colors.navy
  },
  headerStatus: {
    fontSize: 14,
    fontWeight: '800',
    color: Colors.navy,
    backgroundColor: '#fff',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999
  },
  overallRow: {
    flexDirection: 'row',
    gap: 8
  },
  overallBadge: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5
  },
  overallBadgeRed: {
    backgroundColor: Colors.red
  },
  overallBadgeBlue: {
    backgroundColor: Colors.blue
  },
  overallText: {
    color: '#fff',
    fontWeight: '900',
    fontSize: 12
  },
  sectionCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 10,
    gap: 8
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '900',
    color: Colors.navy
  },
  roundCard: {
    backgroundColor: '#f4f7fb',
    borderRadius: 12,
    padding: 10,
    gap: 8
  },
  roundTitle: {
    fontSize: 19,
    fontWeight: '900',
    color: Colors.navy
  },
  competitorSection: {
    borderRadius: 10,
    borderWidth: 2,
    padding: 8,
    gap: 6,
    backgroundColor: '#fff'
  },
  competitorSectionRed: {
    borderColor: Colors.red
  },
  competitorSectionBlue: {
    borderColor: Colors.blue
  },
  sideLabel: {
    alignSelf: 'flex-start',
    minWidth: 62,
    textAlign: 'center',
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 4,
    color: '#fff',
    fontWeight: '900',
    fontSize: 12
  },
  sideLabelRed: {
    backgroundColor: Colors.red
  },
  sideLabelBlue: {
    backgroundColor: Colors.blue
  },
  indicatorsRow: {
    flexDirection: 'row',
    gap: 6
  },
  indicatorPill: {
    flex: 1,
    borderRadius: 8,
    backgroundColor: '#e2e8f0',
    paddingVertical: 6,
    paddingHorizontal: 8,
    gap: 2
  },
  indicatorTotalPill: {
    backgroundColor: '#cbd5e1',
    borderWidth: 1,
    borderColor: '#94a3b8'
  },
  indicatorLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: '#334155'
  },
  indicatorValue: {
    fontSize: 18,
    fontWeight: '900',
    color: Colors.navy
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10
  },
  small: {
    fontSize: 12,
    color: Colors.navy,
    fontWeight: '700'
  },
  buttons: {
    gap: 8
  },
  waitBox: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 12,
    borderWidth: 2,
    borderColor: Colors.blue
  },
  waitTitle: {
    fontSize: 16,
    fontWeight: '900',
    color: Colors.navy
  }
});

function friendlyMatchStatus(status: string) {
  if (status === 'active') return t('matchStatus.active');
  if (status === 'finished_locally') return t('matchStatus.closed');
  if (status === 'finished_locally_pending_finalize_ack') return t('matchStatus.closedPending');
  if (status === 'finalized_acknowledged') return t('matchStatus.finalized');
  if (status === 'finalize_failed_retrying') return t('matchStatus.retrying');
  return status;
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function round2(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function formatTotal(value: number): string {
  return value.toFixed(2);
}
