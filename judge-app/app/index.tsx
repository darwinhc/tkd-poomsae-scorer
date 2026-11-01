import { router } from 'expo-router';
import { useEffect } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Colors } from '@/constants/colors';
import { useAppStore } from '@/store/appStore';
import { t } from '@/i18n';

export default function IndexScreen() {
  const bootstrapped = useAppStore((state) => state.bootstrapped);
  const needsJudgeSetup = useAppStore((state) => state.needsJudgeSetup);
  const activeMatch = useAppStore((state) => state.activeMatch);

  useEffect(() => {
    if (!bootstrapped) {
      return;
    }

    if (needsJudgeSetup) {
      router.replace('/judge-setup');
      return;
    }

    if (activeMatch) {
      router.replace('/technical-scoring');
      return;
    }

    router.replace('/match-setup');
  }, [bootstrapped, needsJudgeSetup, activeMatch]);

  return (
    <View style={styles.container}>
      <ActivityIndicator size="large" color={Colors.navy} />
      <Text style={styles.text}>{t('common.loading')}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.bg,
    gap: 12
  },
  text: {
    fontSize: 18,
    fontWeight: '700',
    color: Colors.navy
  }
});
