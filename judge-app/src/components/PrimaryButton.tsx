import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';
import { Colors } from '@/constants/colors';

export function PrimaryButton({
  title,
  onPress,
  variant = 'dark',
  size = 'normal',
  disabled = false,
  icon,
  testID
}: {
  title: string;
  onPress: () => void;
  variant?: 'dark' | 'green' | 'red' | 'blue' | 'gray';
  size?: 'normal' | 'compact';
  disabled?: boolean;
  icon?: ReactNode;
  testID?: string;
}) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        size === 'compact' ? styles.baseCompact : null,
        styles[variant],
        disabled && styles.disabled,
        pressed && !disabled && styles.pressed
      ]}
    >
      {icon}
      {title ? <Text style={[styles.text, size === 'compact' ? styles.textCompact : null]}>{title}</Text> : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 68,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
    flexDirection: 'row',
    gap: 10
  },
  baseCompact: {
    minHeight: 56,
    borderRadius: 14,
    paddingHorizontal: 14
  },
  text: {
    color: '#fff',
    fontSize: 22,
    fontWeight: '800'
  },
  textCompact: {
    fontSize: 20
  },
  dark: {
    backgroundColor: Colors.navy
  },
  green: {
    backgroundColor: Colors.success
  },
  red: {
    backgroundColor: Colors.red
  },
  blue: {
    backgroundColor: Colors.blue
  },
  gray: {
    backgroundColor: '#556070'
  },
  disabled: {
    opacity: 0.45
  },
  pressed: {
    transform: [{ scale: 0.98 }]
  }
});
