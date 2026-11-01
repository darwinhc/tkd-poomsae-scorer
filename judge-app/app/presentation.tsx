import { useFocusEffect, router } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Ionicons } from '@expo/vector-icons';
import { Alert, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { appFacade } from '@/application/appFacade';
import { PresentationSidePanel } from '@/components/PresentationSidePanel';
import { PrimaryButton } from '@/components/PrimaryButton';
import { ScreenContainer } from '@/components/ScreenContainer';
import { StatusBadge } from '@/components/StatusBadge';
import { Colors } from '@/constants/colors';
import { PRESENTATION_CATEGORY_MAX_SCORE } from '@/constants/defaults';
import type { ScoreTarget } from '@/domain/models/entities';
import { useAppStore } from '@/store/appStore';
import { t } from '@/i18n';
import { errorMessage } from '@/i18n/LocalizedError';

export default function PresentationScreen() {
  const wsStatus = useAppStore((s) => s.wsStatus);
  const { width, height } = useWindowDimensions();
  const isLandscape = width > height;
  const compactPanels = height < 760 || (isLandscape && height < 560);
  const tightLandscape = isLandscape && height < 430;
  const roomyPanels = !compactPanels && (height >= 900 || width >= 1000);
  const compactHeader = isLandscape || height < 760;

  const [actionValue, setActionValue] = useState(0.1);
  const [projection, setProjection] = useState<
    | {
        match: {
          id: string;
          competitorLeftName: string;
          competitorRightName: string;
          currentRound: number;
          totalRounds: number;
          status: string;
        };
        presentation: {
          total: { red: number; blue: number };
          byCategory: {
            speedPower: { red: number; blue: number };
            rhythmTempo: { red: number; blue: number };
            energyExpression: { red: number; blue: number };
          };
        };
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
          currentRound: active.match.currentRound,
          totalRounds: active.match.totalRounds,
          status: active.match.status
        },
        presentation: active.presentation
      });
    } else {
      setProjection(null);
    }
  }, []);

  const load = useCallback(async () => {
    const settings = await appFacade.getSettings();
    setActionValue(settings.actionValue1);
    await refreshProjection();
  }, [refreshProjection]);

  useFocusEffect(
    useCallback(() => {
      load().catch(() => undefined);
      return undefined;
    }, [load])
  );

  const enqueuePresentationTap = useCallback(
    (side: 'RED' | 'BLUE', target: ScoreTarget, delta: number) => {
      if (!projection || projection.match.status !== 'active') return;

      setProjection((prev) => {
        if (!prev) return prev;
        const categoryKey =
          target === 'PRESENTATION_SPEED_POWER'
            ? 'speedPower'
            : target === 'PRESENTATION_RHYTHM_TEMPO'
              ? 'rhythmTempo'
              : 'energyExpression';
        const current = prev.presentation.byCategory[categoryKey];
        const nextCategory = {
          ...current,
          [side === 'RED' ? 'red' : 'blue']: clamp(
            round1((side === 'RED' ? current.red : current.blue) + delta),
            0,
            PRESENTATION_CATEGORY_MAX_SCORE
          )
        };
        const nextByCategory = {
          ...prev.presentation.byCategory,
          [categoryKey]: nextCategory
        };
        const nextTotal = {
          red: round1(nextByCategory.speedPower.red + nextByCategory.rhythmTempo.red + nextByCategory.energyExpression.red),
          blue: round1(nextByCategory.speedPower.blue + nextByCategory.rhythmTempo.blue + nextByCategory.energyExpression.blue)
        };

        return {
          ...prev,
          presentation: {
            byCategory: nextByCategory,
            total: nextTotal
          }
        };
      });

      scoreQueueRef.current = scoreQueueRef.current
        .then(async () => {
          await appFacade.applyScore(side, delta, target);
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

  const withTapGuard = async (fn: () => Promise<void>) => {
    if (lockRef.current) return;
    lockRef.current = true;
    try {
      await fn();
    } finally {
      setTimeout(() => {
        lockRef.current = false;
      }, 180);
    }
  };

  if (!projection) {
    return (
      <ScreenContainer>
        <Text style={styles.title}>{t('presentation.noActiveMatch')}</Text>
        <PrimaryButton title={t('presentation.backToTechnique')} onPress={() => router.replace('/technical-scoring')} />
      </ScreenContainer>
    );
  }

  const disableScoring = projection.match.status !== 'active';
  const roundLabel = `R${projection.match.currentRound}/${projection.match.totalRounds}`;
  const isLastRound = projection.match.currentRound >= projection.match.totalRounds;

  return (
    <ScreenContainer scroll={false} contentStyle={isLandscape ? styles.landscapeContainer : styles.portraitContainer}>
      <View style={styles.topRow}>
        <Text style={[styles.title, compactHeader && styles.titleCompact]}>{t('common.presentation')}</Text>
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
            onPress={() => router.push({ pathname: '/connection', params: { returnTo: 'presentation' } })}
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

      <View style={[styles.sidesRow, isLandscape ? styles.sidesRowLandscape : styles.sidesRowPortrait, tightLandscape && styles.sidesRowTight]}>
        <PresentationSidePanel
          side="RED"
          name={projection.match.competitorLeftName}
          presentation={{
            total: projection.presentation.total.red,
            speedPower: projection.presentation.byCategory.speedPower.red,
            rhythmTempo: projection.presentation.byCategory.rhythmTempo.red,
            energyExpression: projection.presentation.byCategory.energyExpression.red
          }}
          actionValue={actionValue}
          onPresentationDelta={(target, delta) => enqueuePresentationTap('RED', target, delta)}
          lock={disableScoring}
          testPrefix="red"
          maxCategoryScore={PRESENTATION_CATEGORY_MAX_SCORE}
          compact={compactPanels}
          roomy={roomyPanels}
          tight={tightLandscape}
        />
        <PresentationSidePanel
          side="BLUE"
          name={projection.match.competitorRightName}
          presentation={{
            total: projection.presentation.total.blue,
            speedPower: projection.presentation.byCategory.speedPower.blue,
            rhythmTempo: projection.presentation.byCategory.rhythmTempo.blue,
            energyExpression: projection.presentation.byCategory.energyExpression.blue
          }}
          actionValue={actionValue}
          onPresentationDelta={(target, delta) => enqueuePresentationTap('BLUE', target, delta)}
          lock={disableScoring}
          testPrefix="blue"
          maxCategoryScore={PRESENTATION_CATEGORY_MAX_SCORE}
          compact={compactPanels}
          roomy={roomyPanels}
          tight={tightLandscape}
        />
      </View>

      <View style={[styles.controlRow, tightLandscape && styles.controlRowTight]}>
        <View style={[styles.controlItem, styles.backControlItem]}>
          <PrimaryButton
            testID="back-technique-btn"
            title=""
            variant="gray"
            size="compact"
            icon={<Ionicons name="arrow-back" size={24} color="#fff" />}
            onPress={() => router.replace('/technical-scoring')}
          />
        </View>
        <View style={[styles.controlItem, styles.resetControlItem]}>
          <PrimaryButton
            testID="reset-presentation-btn"
            title={t('common.reset')}
            variant="gray"
            size="compact"
            onPress={() => {
              Alert.alert(t('presentation.resetTitle'), t('presentation.resetMessage'), [
                { text: t('common.no'), style: 'cancel' },
                {
                  text: t('presentation.resetConfirm'),
                  style: 'destructive',
                  onPress: () => {
                    withTapGuard(async () => {
                      await appFacade.resetPresentationRound();
                      await load();
                    }).catch(() => undefined);
                  }
                }
              ]);
            }}
            disabled={disableScoring}
          />
        </View>
        <View style={[styles.controlItem, styles.nextControlItem]}>
          <PrimaryButton
            testID={isLastRound ? 'finalize-btn' : 'next-round-btn'}
            title={isLastRound ? t('presentation.finish') : ''}
            variant={isLastRound ? 'green' : 'blue'}
            size="compact"
            icon={isLastRound ? undefined : <Ionicons name="arrow-forward" size={24} color="#fff" />}
            onPress={() => {
              if (isLastRound) {
                Alert.alert(t('presentation.finishTitle'), t('presentation.finishMessage'), [
                  { text: t('common.cancel'), style: 'cancel' },
                  {
                    text: t('presentation.finishConfirm'),
                    style: 'default',
                    onPress: () => {
                      withTapGuard(async () => {
                        await appFacade.finalizeMatch();
                        router.replace({ pathname: '/summary', params: { matchId: projection.match.id } });
                      }).catch((error: any) => Alert.alert(t('common.error'), errorMessage(error)));
                    }
                  }
                ]);
                return;
              }

              withTapGuard(async () => {
                await appFacade.nextRound();
                router.replace('/technical-scoring');
              }).catch(() => {
                Alert.alert(t('presentation.notAllowedTitle'), t('presentation.lastRoundMessage'));
              });
            }}
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
    fontSize: 32,
    fontWeight: '900',
    color: Colors.navy
  },
  titleCompact: {
    fontSize: 20
  },
  roundTop: {
    fontSize: 26,
    fontWeight: '900',
    color: Colors.navy
  },
  roundTopCompact: {
    fontSize: 18
  },
  roundBottom: {
    fontSize: 28,
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
    paddingHorizontal: 8,
    paddingTop: 6,
    paddingBottom: 6,
    gap: 8
  },
  landscapeContainer: {
    flex: 1,
    paddingHorizontal: 1,
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
    gap: 6
  },
  sidesRowLandscape: {
    gap: 3
  },
  sidesRowTight: {
    gap: 2
  },
  controlRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 6,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: '#CBD5E1'
  },
  controlRowTight: {
    marginTop: 4,
    paddingTop: 4
  },
  controlItem: {
    flex: 1
  },
  backControlItem: {
    flex: 0.7
  },
  resetControlItem: {
    flex: 0.9
  },
  nextControlItem: {
    flex: 1.1
  }
});

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
