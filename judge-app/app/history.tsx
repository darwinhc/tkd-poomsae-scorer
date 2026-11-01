import { useFocusEffect, router } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { appFacade } from '@/application/appFacade';
import { PrimaryButton } from '@/components/PrimaryButton';
import { ScreenContainer } from '@/components/ScreenContainer';
import { Colors } from '@/constants/colors';
import { t } from '@/i18n';

export default function HistoryScreen() {
  const [matches, setMatches] = useState<any[]>([]);

  useFocusEffect(
    useCallback(() => {
      appFacade.listHistory().then(setMatches).catch(() => undefined);
      return undefined;
    }, [])
  );

  return (
    <ScreenContainer>
      <Text testID="history-title" style={styles.title}>
        {t('history.title')}
      </Text>
      <Section title={t('history.sectionActive')} data={matches.filter((m) => m.status === 'active')} />
      <Section
        title={t('history.sectionPending')}
        data={matches.filter((m) =>
          ['finished_locally', 'finished_locally_pending_finalize_ack', 'finalize_failed_retrying'].includes(m.status)
        )}
      />
      <Section title={t('history.sectionFinalized')} data={matches.filter((m) => m.status === 'finalized_acknowledged')} />

      <PrimaryButton testID="history-back-btn" title={t('common.back')} variant="gray" onPress={() => router.back()} />
    </ScreenContainer>
  );
}

function Section({ title, data }: { title: string; data: any[] }) {
  if (!data.length) {
    return null;
  }
  return (
    <View style={{ gap: 8 }}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {data.map((match) => (
        <Pressable
          testID={`history-item-${match.id}`}
          key={match.id}
          style={styles.item}
          onPress={() => router.push({ pathname: '/summary', params: { matchId: match.id } })}
        >
          <Text style={styles.itemMain}>
            {t('common.versus', { left: match.competitorLeftName, right: match.competitorRightName })}
          </Text>
          <Text style={styles.itemSecondary}>{`R${match.currentRound}/${match.totalRounds} · ${friendlyMatchStatus(match.status)}`}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  title: {
    fontSize: 38,
    fontWeight: '900',
    color: Colors.navy
  },
  item: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 12,
    borderWidth: 1,
    borderColor: '#CBD5E1',
    minHeight: 82,
    justifyContent: 'center'
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '900',
    color: Colors.navy
  },
  itemMain: {
    fontSize: 20,
    fontWeight: '800',
    color: Colors.navy
  },
  itemSecondary: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.subtle
  }
});

function friendlyMatchStatus(status: string) {
  if (status === 'active') return t('matchStatus.active');
  if (status === 'finished_locally') return t('matchStatus.closed');
  if (status === 'finished_locally_pending_finalize_ack') return t('matchStatus.pending');
  if (status === 'finalized_acknowledged') return t('matchStatus.finalized');
  if (status === 'finalize_failed_retrying') return t('matchStatus.retrying');
  return status;
}
