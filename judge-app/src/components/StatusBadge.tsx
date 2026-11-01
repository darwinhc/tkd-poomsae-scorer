import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';
import { Colors } from '@/constants/colors';

export function StatusBadge({
  label,
  tone,
  compact = false,
  icon,
  onPress,
  testID
}: {
  label: string;
  tone: 'ok' | 'warn' | 'error' | 'neutral';
  compact?: boolean;
  icon?: ReactNode;
  onPress?: () => void;
  testID?: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={!onPress}
      accessibilityRole={onPress ? 'button' : undefined}
      style={({ pressed }) => [
        styles.base,
        compact && styles.baseCompact,
        toneStyles[tone],
        pressed && onPress ? styles.pressed : null
      ]}
    >
      {icon}
      <Text style={[styles.text, compact && styles.textCompact]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6
  },
  baseCompact: {
    paddingHorizontal: 9,
    paddingVertical: 4
  },
  text: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 12
  },
  textCompact: {
    fontSize: 11
  },
  pressed: {
    opacity: 0.85,
    transform: [{ scale: 0.98 }]
  }
});

const toneStyles = StyleSheet.create({
  ok: { backgroundColor: Colors.success },
  warn: { backgroundColor: Colors.warning },
  error: { backgroundColor: Colors.danger },
  neutral: { backgroundColor: '#64748B' }
});
