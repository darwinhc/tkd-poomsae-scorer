import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { AthleteSide } from '@/domain/models/entities';
import { Colors } from '@/constants/colors';
import { t } from '@/i18n';

export function ScoreSidePanel({
  side,
  slot,
  name,
  techniqueScore,
  actionValues,
  onTechniqueDelta,
  lock,
  testPrefix,
  compact = false,
  roomy = false
}: {
  side: AthleteSide;
  slot?: 'LEFT' | 'RIGHT';
  name: string;
  techniqueScore: number;
  actionValues: [number, number];
  onTechniqueDelta: (delta: number) => void;
  lock: boolean;
  testPrefix: string;
  compact?: boolean;
  roomy?: boolean;
}) {
  const isRed = side === 'RED';
  const bg = isRed ? Colors.red : Colors.blue;
  const bgDark = isRed ? Colors.redDark : Colors.blueDark;
  const deductionOnLeft = (slot ?? 'LEFT') === 'LEFT';

  const deductionColumn = (
    <View style={styles.column}>
      <DeltaButton
        testID={`${testPrefix}-minus-1`}
        color={bgDark}
        label={`-${actionValues[0].toFixed(1)}`}
        onTap={() => onTechniqueDelta(-actionValues[0])}
        disabled={lock}
        compact={compact}
        roomy={roomy}
      />
      <DeltaButton
        testID={`${testPrefix}-minus-2`}
        color={bgDark}
        label={`-${actionValues[1].toFixed(1)}`}
        onTap={() => onTechniqueDelta(-actionValues[1])}
        disabled={lock}
        compact={compact}
        roomy={roomy}
      />
    </View>
  );

  const correctionColumn = (
    <View style={styles.column}>
      <DeltaButton
        testID={`${testPrefix}-plus-1`}
        color={bg}
        label={`+${actionValues[0].toFixed(1)}`}
        onTap={() => onTechniqueDelta(actionValues[0])}
        disabled={lock}
        compact={compact}
        roomy={roomy}
      />
      <DeltaButton
        testID={`${testPrefix}-plus-2`}
        color={bg}
        label={`+${actionValues[1].toFixed(1)}`}
        onTap={() => onTechniqueDelta(actionValues[1])}
        disabled={lock}
        compact={compact}
        roomy={roomy}
      />
    </View>
  );

  return (
    <View style={[styles.panel, { borderColor: bgDark }, compact && styles.panelCompact]}>
      <View style={[styles.scoreBox, { backgroundColor: bg }, compact && styles.scoreBoxCompact]}>
        <View style={styles.headerInline}>
          <Text style={[styles.name, compact && styles.nameCompact]}>{name || (isRed ? t('common.redUpper') : t('common.blueUpper'))}</Text>
          <Text style={[styles.score, compact && styles.scoreCompact]}>{techniqueScore.toFixed(1)}</Text>
        </View>
      </View>

      <View style={styles.columnsRow}>
        {deductionOnLeft ? deductionColumn : correctionColumn}
        {deductionOnLeft ? correctionColumn : deductionColumn}
      </View>
    </View>
  );
}

function DeltaButton({
  label,
  onTap,
  color,
  disabled,
  testID,
  compact,
  roomy
}: {
  label: string;
  onTap: () => void;
  color: string;
  disabled: boolean;
  testID: string;
  compact: boolean;
  roomy: boolean;
}) {
  return (
    <Pressable
      testID={testID}
      disabled={disabled}
      android_disableSound
      style={({ pressed }) => [
        styles.action,
        compact && styles.actionCompact,
        roomy && !compact && styles.actionRoomy,
        { backgroundColor: color },
        disabled && styles.disabled,
        pressed && styles.pressed
      ]}
      onPressIn={onTap}
    >
      <Text style={[styles.actionText, compact && styles.actionTextCompact, roomy && !compact && styles.actionTextRoomy]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  panel: {
    flex: 1,
    borderRadius: 18,
    padding: 8,
    gap: 6,
    borderWidth: 2,
    backgroundColor: '#fff'
  },
  panelCompact: {
    padding: 4,
    borderRadius: 12,
    gap: 5
  },
  scoreBox: {
    borderRadius: 16,
    minHeight: 70,
    justifyContent: 'center',
    paddingHorizontal: 10
  },
  scoreBoxCompact: {
    minHeight: 52,
    paddingHorizontal: 8
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
  score: {
    color: '#fff',
    fontSize: 28,
    fontWeight: '900'
  },
  scoreCompact: {
    fontSize: 20
  },
  columnsRow: {
    flexDirection: 'row',
    gap: 6,
    flex: 1
  },
  column: {
    flex: 1,
    gap: 6
  },
  action: {
    flex: 1,
    minHeight: 46,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center'
  },
  actionCompact: {
    minHeight: 38,
    borderRadius: 9
  },
  actionRoomy: {
    minHeight: 62,
    borderRadius: 16
  },
  actionText: {
    color: '#fff',
    fontSize: 22,
    fontWeight: '800'
  },
  actionTextCompact: {
    fontSize: 17
  },
  actionTextRoomy: {
    fontSize: 28
  },
  disabled: {
    opacity: 0.5
  },
  pressed: {
    transform: [{ scale: 0.98 }]
  }
});
