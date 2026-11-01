import { useFocusEffect, router } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Ionicons } from '@expo/vector-icons';
import { Alert, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { appFacade } from '@/application/appFacade';
import { PrimaryButton } from '@/components/PrimaryButton';
import { ScoreSidePanel } from '@/components/ScoreSidePanel';
import { ScreenContainer } from '@/components/ScreenContainer';
import { StatusBadge } from '@/components/StatusBadge';
import { Colors } from '@/constants/colors';
import { useAppStore } from '@/store/appStore';
import { t } from '@/i18n';
import { errorMessage } from '@/i18n/LocalizedError';

export default function TechnicalScoringScreen() {
  const wsStatus = useAppStore((s) => s.wsStatus);
  const { width, height } = useWindowDimensions();
  const isLandscape = width > height;
  const compactPanels = height < 760 || (isLandscape && height < 560);
  const roomyPanels = !compactPanels && (height >= 900 || width >= 1000);
  const compactHeader = isLandscape || height < 760;

  const [actionValues, setActionValues] = useState<[number, number]>([0.1, 0.3]);
  const [projection, setProjection] = useState<
    | {
        match: {
          id: string;
          competitorLeftName: string;
          competitorRightName: string;
          leftSideColor: 'RED' | 'BLUE';
          rightSideColor: 'RED' | 'BLUE';
          currentRound: number;
          totalRounds: number;
          status: string;
          maxTechniqueScore: number;
        };
        technique: { red: number; blue: number };
      }
    | null
  >(null);

  const lockRef = useRef(false);
  const scoreQueueRef = useRef<Promise<void>>(Promise.resolve());

  const refreshProjection = useCallback(async () => {
    const active = await appFacade.getActiveScoring();
    if (active?.match) {
      setProjection({
        match: {
          id: active.match.id,
          competitorLeftName: active.match.competitorLeftName,
          competitorRightName: active.match.competitorRightName,
          leftSideColor: active.match.leftSideColor,
          rightSideColor: active.match.rightSideColor,
          currentRound: active.match.currentRound,
          totalRounds: active.match.totalRounds,
          status: active.match.status,
          maxTechniqueScore: active.match.startingScore
        },
        technique: active.technique
      });
    } else {
      setProjection(null);
    }
  }, []);

  const load = useCallback(async () => {
    const settings = await appFacade.getSettings();
    setActionValues([settings.actionValue1, settings.actionValue2]);
    await refreshProjection();
  }, [refreshProjection]);

  useFocusEffect(
    useCallback(() => {
      load().catch(() => undefined);
      return undefined;
    }, [load])
  );

  const withTapGuard = async (fn: () => Promise<void>) => {
    if (lockRef.current) return;
    lockRef.current = true;
    try {
      await fn();
      await load();
    } finally {
      setTimeout(() => {
        lockRef.current = false;
      }, 180);
    }
  };

  const enqueueTechniqueTap = useCallback(
    (side: 'RED' | 'BLUE', delta: number) => {
      if (!projection || projection.match.status !== 'active') return;

      setProjection((prev) => {
        if (!prev) return prev;
        if (side === 'RED') {
          return {
            ...prev,
            technique: {
              ...prev.technique,
              red: clamp(round1(prev.technique.red + delta), 0, prev.match.maxTechniqueScore)
            }
          };
        }
        return {
          ...prev,
          technique: {
            ...prev.technique,
            blue: clamp(round1(prev.technique.blue + delta), 0, prev.match.maxTechniqueScore)
          }
        };
      });

      scoreQueueRef.current = scoreQueueRef.current
        .then(async () => {
          await appFacade.applyScore(side, delta, 'TECHNIQUE');
          await refreshProjection();
        })
        .catch((error: any) => {
          refreshProjection().catch(() => undefined);
          Alert.alert(t('common.error'), errorMessage(error));
        });
    },
    [projection, refreshProjection]
  );

  const isConnected = wsStatus === 'connected';
  const connectionLabel =
    wsStatus === 'connected' ? t('status.connected') : wsStatus === 'connecting' ? t('status.reconnecting') : t('status.notConnected');
  const connectionTone = wsStatus === 'connected' ? 'ok' : wsStatus === 'connecting' ? 'neutral' : 'warn';
  const connectionIconName = wsStatus === 'connected' ? 'wifi' : wsStatus === 'connecting' ? 'sync' : 'cloud-offline-outline';

  if (!projection) {
    return (
      <ScreenContainer>
        <Text style={styles.title}>{t('technicalScoring.noActiveMatch')}</Text>
        <PrimaryButton title={t('technicalScoring.setUpMatch')} onPress={() => router.replace('/match-setup')} />
        <PrimaryButton title={t('connection.title')} variant="gray" onPress={() => router.replace('/connection')} />
      </ScreenContainer>
    );
  }

  const disableScoring = projection.match.status !== 'active';
  const roundLabel = `R${projection.match.currentRound}/${projection.match.totalRounds}`;
  const leftSide = projection.match.leftSideColor;
  const rightSide = projection.match.rightSideColor;
  const leftScore = leftSide === 'RED' ? projection.technique.red : projection.technique.blue;
  const rightScore = rightSide === 'RED' ? projection.technique.red : projection.technique.blue;

  return (
    <ScreenContainer scroll={false} contentStyle={isLandscape ? styles.landscapeContainer : styles.portraitContainer}>
      <View style={styles.topRow}>
        <Text style={[styles.title, compactHeader && styles.titleCompact]}>{t('common.technique')}</Text>
        {isLandscape ? <Text style={[styles.roundTop, compactHeader && styles.roundTopCompact]}>{roundLabel}</Text> : null}
        <View style={styles.badges}>
          <StatusBadge
            testID="connection-badge"
            label={connectionLabel}
            tone={connectionTone}
            compact={compactHeader}
            icon={
              <Ionicons
                name={connectionIconName}
                size={compactHeader ? 12 : 14}
                color="#fff"
              />
            }
            onPress={() => router.push({ pathname: '/connection', params: { returnTo: 'technical-scoring' } })}
          />
          <Pressable
            testID="close-screen-btn"
            style={styles.closeBtn}
            hitSlop={8}
            onPress={() => {
              Alert.alert(t('closeMatch.title'), t('closeMatch.message'), [
                { text: t('common.no'), style: 'cancel' },
                {
                  text: t('closeMatch.confirm'),
                  style: 'destructive',
                  onPress: () => {
                    setProjection(null);
                    appFacade
                      .closeActiveMatch()
                      .catch(() => undefined)
                      .finally(() => {
                        router.replace('/match-setup');
                      });
                  }
                }
              ]);
            }}
          >
            <Ionicons name="close" size={24} color={Colors.navy} />
          </Pressable>
        </View>
      </View>

      {!isLandscape ? <Text style={[styles.roundBottom, compactHeader && styles.roundBottomCompact]}>{roundLabel}</Text> : null}

      <View style={[styles.sidesRow, isLandscape ? styles.sidesRowLandscape : styles.sidesRowPortrait]}>
        <ScoreSidePanel
          side={leftSide}
          slot="LEFT"
          name={projection.match.competitorLeftName}
          techniqueScore={leftScore}
          actionValues={actionValues}
          onTechniqueDelta={(delta) => enqueueTechniqueTap(leftSide, delta)}
          lock={disableScoring}
          testPrefix="red"
          compact={compactPanels}
          roomy={roomyPanels}
        />
        <ScoreSidePanel
          side={rightSide}
          slot="RIGHT"
          name={projection.match.competitorRightName}
          techniqueScore={rightScore}
          actionValues={actionValues}
          onTechniqueDelta={(delta) => enqueueTechniqueTap(rightSide, delta)}
          lock={disableScoring}
          testPrefix="blue"
          compact={compactPanels}
          roomy={roomyPanels}
        />
      </View>

      <View style={isLandscape ? styles.controlRow : styles.controlColumn}>
        <View style={styles.controlItem}>
          <PrimaryButton
            testID="reset-btn"
            title={t('common.reset')}
            variant="gray"
            size="compact"
            onPress={() => {
              Alert.alert(t('technicalScoring.resetTitle'), t('technicalScoring.resetMessage'), [
                { text: t('common.cancel'), style: 'cancel' },
                {
                  text: t('common.reset'),
                  style: 'destructive',
                  onPress: () => {
                    withTapGuard(async () => {
                      await appFacade.resetTechniqueRound();
                    }).catch(() => undefined);
                  }
                }
              ]);
            }}
            disabled={disableScoring}
          />
        </View>

        <View style={styles.controlItem}>
          <PrimaryButton
            testID="next-presentation-btn"
            title=""
            variant="green"
            size="compact"
            icon={<Ionicons name="arrow-forward" size={24} color="#fff" />}
            onPress={() => router.push('/presentation')}
            disabled={disableScoring}
          />
        </View>
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 6
  },
  title: {
    fontSize: 34,
    fontWeight: '900',
    color: Colors.navy
  },
  titleCompact: {
    fontSize: 20
  },
  roundTop: {
    fontSize: 28,
    fontWeight: '900',
    color: Colors.navy
  },
  roundTopCompact: {
    fontSize: 18
  },
  roundBottom: {
    fontSize: 30,
    textAlign: 'center',
    fontWeight: '900',
    color: Colors.navy
  },
  roundBottomCompact: {
    fontSize: 24
  },
  badges: {
    flexDirection: 'row',
    gap: 4,
    alignItems: 'center'
  },
  closeBtn: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center'
  },
  portraitContainer: {
    flex: 1,
    paddingHorizontal: 6,
    paddingTop: 6,
    paddingBottom: 6,
    gap: 8
  },
  landscapeContainer: {
    flex: 1,
    paddingHorizontal: 0,
    paddingTop: 1,
    paddingBottom: 3,
    gap: 4
  },
  sidesRow: {
    flexDirection: 'row',
    minHeight: 0,
    flex: 1
  },
  sidesRowPortrait: {
    gap: 5
  },
  sidesRowLandscape: {
    gap: 2
  },
  controlColumn: {
    flexDirection: 'row',
    gap: 8
  },
  controlRow: {
    flexDirection: 'row',
    gap: 8
  },
  controlItem: {
    flex: 1
  }
});

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
