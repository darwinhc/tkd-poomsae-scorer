import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { AthleteSide, ScoreTarget } from '@/domain/models/entities';
import { Colors } from '@/constants/colors';
import { t } from '@/i18n';

type PresentationScores = {
  speedPower: number;
  rhythmTempo: number;
  energyExpression: number;
  total: number;
};

export function PresentationSidePanel({
  side,
  name,
  presentation,
  actionValue,
  onPresentationDelta,
  lock,
  testPrefix,
  maxCategoryScore = 2,
  compact = false,
  roomy = false,
  tight = false
}: {
  side: AthleteSide;
  name: string;
  presentation: PresentationScores;
  actionValue: number;
  onPresentationDelta: (target: ScoreTarget, delta: number) => void;
  lock: boolean;
  testPrefix: string;
  maxCategoryScore?: number;
  compact?: boolean;
  roomy?: boolean;
  tight?: boolean;
}) {
  const isRed = side === 'RED';
  const bg = isRed ? Colors.red : Colors.blue;
  const bgDark = isRed ? Colors.redDark : Colors.blueDark;

  return (
    <View style={[styles.panel, { borderColor: bgDark }, compact && styles.panelCompact]}>
      <View style={[styles.header, { backgroundColor: bg }, compact && styles.headerCompact]}>
        <View style={styles.headerInline}>
          <Text style={[styles.name, compact && styles.nameCompact]}>{name || (isRed ? t('common.redUpper') : t('common.blueUpper'))}</Text>
          <Text style={[styles.total, compact && styles.totalCompact]}>{presentation.total.toFixed(2)}</Text>
        </View>
      </View>

      <PresentationRow
        label={tight ? t('presentation.speedPowerShort') : t('presentation.speedPower')}
        value={presentation.speedPower}
        onDelta={(delta) => onPresentationDelta('PRESENTATION_SPEED_POWER', delta)}
        step={actionValue}
        max={maxCategoryScore}
        compact={compact}
        roomy={roomy}
        tight={tight}
        color={bgDark}
        disabled={lock}
        testIDPrefix={`${testPrefix}-presentation-speed`}
      />
      <PresentationRow
        label={t('presentation.rhythmTempo')}
        value={presentation.rhythmTempo}
        onDelta={(delta) => onPresentationDelta('PRESENTATION_RHYTHM_TEMPO', delta)}
        step={actionValue}
        max={maxCategoryScore}
        compact={compact}
        roomy={roomy}
        tight={tight}
        color={bgDark}
        disabled={lock}
        testIDPrefix={`${testPrefix}-presentation-rhythm`}
      />
      <PresentationRow
        label={t('presentation.energyExpression')}
        value={presentation.energyExpression}
        onDelta={(delta) => onPresentationDelta('PRESENTATION_ENERGY_EXPRESSION', delta)}
        step={actionValue}
        max={maxCategoryScore}
        compact={compact}
        roomy={roomy}
        tight={tight}
        color={bgDark}
        disabled={lock}
        testIDPrefix={`${testPrefix}-presentation-energy`}
      />
    </View>
  );
}

function PresentationRow({
  label,
  value,
  onDelta,
  step,
  max,
  compact,
  roomy,
  tight,
  color,
  disabled,
  testIDPrefix
}: {
  label: string;
  value: number;
  onDelta: (delta: number) => void;
  step: number;
  max: number;
  compact: boolean;
  roomy: boolean;
  tight: boolean;
  color: string;
  disabled: boolean;
  testIDPrefix: string;
}) {
  const MIN = 0;
  const MAX = max;
  const [barWidth, setBarWidth] = useState(1);
  const [draftValue, setDraftValue] = useState<number | null>(null);

  const shownValue = draftValue ?? value;
  const ratio = useMemo(() => Math.max(0, Math.min(1, (shownValue - MIN) / (MAX - MIN))), [shownValue]);

  const valueFromPosition = (locationX: number) => {
    const clampedX = Math.max(0, Math.min(locationX, barWidth));
    const raw = MIN + (clampedX / Math.max(1, barWidth)) * (MAX - MIN);
    return clamp(roundToStep(raw, step), MIN, MAX);
  };

  const previewAt = (locationX: number) => {
    if (disabled) return;
    setDraftValue(valueFromPosition(locationX));
  };

  const commitAt = (locationX: number) => {
    if (disabled) return;
    const nextValue = valueFromPosition(locationX);
    setDraftValue(null);
    const delta = round1(nextValue - value);
    if (Math.abs(delta) < 0.05) return;
    onDelta(delta);
  };

  return (
    <View style={[styles.presentationRow, tight && styles.presentationRowTight]}>
      <Text style={[styles.presentationLabel, tight && styles.presentationLabelTight]}>{label}</Text>
      <View style={[styles.controls, tight && styles.controlsTight]}>
        <Pressable
          testID={`${testIDPrefix}-minus`}
          style={[
            styles.smallButton,
            compact && styles.smallButtonCompact,
            tight && styles.smallButtonTight,
            roomy && !compact && !tight && styles.smallButtonRoomy,
            { backgroundColor: color }
          ]}
          disabled={disabled}
          android_disableSound
          onPressIn={() => onDelta(-step)}
        >
          <Text
            style={[
              styles.smallButtonText,
              compact && styles.smallButtonTextCompact,
              tight && styles.smallButtonTextTight,
              roomy && !compact && !tight && styles.smallButtonTextRoomy
            ]}
          >
            -
          </Text>
        </Pressable>
        <View
          testID={`${testIDPrefix}-bar`}
          style={[styles.barWrap, compact && styles.barWrapCompact, tight && styles.barWrapTight]}
          onLayout={(event) => {
            setBarWidth(event.nativeEvent.layout.width);
          }}
          onStartShouldSetResponder={() => !disabled}
          onMoveShouldSetResponder={() => !disabled}
          onResponderGrant={(event) => previewAt(event.nativeEvent.locationX)}
          onResponderMove={(event) => previewAt(event.nativeEvent.locationX)}
          onResponderRelease={(event) => commitAt(event.nativeEvent.locationX)}
          onResponderTerminate={() => setDraftValue(null)}
        >
          <View style={[styles.barFill, { width: `${ratio * 100}%`, backgroundColor: color }]} />
          <Text style={[styles.barText, compact && styles.barTextCompact, tight && styles.barTextTight]}>{shownValue.toFixed(1)}</Text>
        </View>
        <Pressable
          testID={`${testIDPrefix}-plus`}
          style={[
            styles.smallButton,
            compact && styles.smallButtonCompact,
            tight && styles.smallButtonTight,
            roomy && !compact && !tight && styles.smallButtonRoomy,
            { backgroundColor: color }
          ]}
          disabled={disabled}
          android_disableSound
          onPressIn={() => onDelta(step)}
        >
          <Text
            style={[
              styles.smallButtonText,
              compact && styles.smallButtonTextCompact,
              tight && styles.smallButtonTextTight,
              roomy && !compact && !tight && styles.smallButtonTextRoomy
            ]}
          >
            +
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

function roundToStep(value: number, step: number): number {
  const safeStep = Math.max(0.1, step);
  return Math.round(value / safeStep) * safeStep;
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

const styles = StyleSheet.create({
  panel: {
    flex: 1,
    borderRadius: 16,
    padding: 8,
    gap: 8,
    borderWidth: 2,
    backgroundColor: '#fff'
  },
  panelCompact: {
    padding: 5,
    gap: 6
  },
  header: {
    borderRadius: 14,
    minHeight: 70,
    justifyContent: 'center',
    paddingHorizontal: 10
  },
  headerCompact: {
    minHeight: 52
  },
  headerInline: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between'
  },
  name: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '800'
  },
  nameCompact: {
    fontSize: 14
  },
  total: {
    color: '#fff',
    fontSize: 30,
    fontWeight: '900'
  },
  totalCompact: {
    fontSize: 22
  },
  presentationRow: {
    gap: 4
  },
  presentationRowTight: {
    gap: 2
  },
  presentationLabel: {
    fontSize: 14,
    fontWeight: '800',
    color: Colors.navy
  },
  presentationLabelTight: {
    fontSize: 12
  },
  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6
  },
  controlsTight: {
    gap: 4
  },
  smallButton: {
    width: 48,
    height: 40,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center'
  },
  smallButtonCompact: {
    width: 40,
    height: 34
  },
  smallButtonTight: {
    width: 36,
    height: 30,
    borderRadius: 8
  },
  smallButtonRoomy: {
    width: 60,
    height: 52
  },
  smallButtonText: {
    color: '#fff',
    fontSize: 28,
    fontWeight: '900',
    lineHeight: 30
  },
  smallButtonTextCompact: {
    fontSize: 20,
    lineHeight: 22
  },
  smallButtonTextTight: {
    fontSize: 18,
    lineHeight: 20
  },
  smallButtonTextRoomy: {
    fontSize: 34,
    lineHeight: 36
  },
  barWrap: {
    flex: 1,
    height: 40,
    borderRadius: 10,
    backgroundColor: '#E2E8F0',
    overflow: 'hidden',
    justifyContent: 'center'
  },
  barWrapCompact: {
    height: 34
  },
  barWrapTight: {
    height: 30,
    borderRadius: 8
  },
  barFill: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0
  },
  barText: {
    textAlign: 'center',
    fontSize: 17,
    fontWeight: '900',
    color: Colors.navy
  },
  barTextCompact: {
    fontSize: 14
  },
  barTextTight: {
    fontSize: 13
  }
});
