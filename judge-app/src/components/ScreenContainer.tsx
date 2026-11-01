import type { PropsWithChildren } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Colors } from '@/constants/colors';

export function ScreenContainer({
  children,
  scroll = true,
  contentStyle,
  keyboardAware = false
}: PropsWithChildren<{ scroll?: boolean; contentStyle?: StyleProp<ViewStyle>; keyboardAware?: boolean }>) {
  const content = scroll ? (
    <ScrollView contentContainerStyle={[styles.scroll, contentStyle]} keyboardShouldPersistTaps="handled">
      {children}
    </ScrollView>
  ) : (
    <View style={[styles.scroll, contentStyle]}>{children}</View>
  );

  return (
    <SafeAreaView style={styles.safe}>
      {keyboardAware ? (
        <KeyboardAvoidingView style={styles.keyboardWrap} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
          {content}
        </KeyboardAvoidingView>
      ) : (
        content
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: Colors.bg
  },
  keyboardWrap: {
    flex: 1
  },
  scroll: {
    padding: 16,
    gap: 14
  }
});
