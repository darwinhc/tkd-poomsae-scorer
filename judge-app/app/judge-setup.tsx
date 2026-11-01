import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, StyleSheet, Text, TextInput, View } from 'react-native';
import { appFacade } from '@/application/appFacade';
import { Colors } from '@/constants/colors';
import { PrimaryButton } from '@/components/PrimaryButton';
import { ScreenContainer } from '@/components/ScreenContainer';
import { t } from '@/i18n';
import { errorMessage } from '@/i18n/LocalizedError';

export default function JudgeSetupScreen() {
  const [judgeName, setJudgeName] = useState('');
  const [saving, setSaving] = useState(false);

  const onSave = async () => {
    if (judgeName.trim().length < 2) {
      Alert.alert(t('judgeSetup.nameRequiredTitle'), t('judgeSetup.nameRequiredMessage'));
      return;
    }

    setSaving(true);
    try {
      await appFacade.saveJudgeName(judgeName.trim());
      router.replace('/match-setup');
    } catch (error: any) {
      Alert.alert(t('common.error'), errorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <ScreenContainer>
      <View style={styles.header}>
        <Text style={styles.title}>{t('judgeSetup.title')}</Text>
        <Text style={styles.subtitle}>{t('judgeSetup.subtitle')}</Text>
      </View>

      <TextInput
        testID="judge-name-input"
        value={judgeName}
        onChangeText={setJudgeName}
        placeholder={t('judgeSetup.namePlaceholder')}
        style={styles.input}
        autoCapitalize="words"
      />

      <PrimaryButton
        testID="judge-save-btn"
        title={saving ? t('common.saving') : t('common.continue')}
        onPress={onSave}
        disabled={saving}
      />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  header: {
    marginTop: 20,
    marginBottom: 10,
    gap: 8
  },
  title: {
    fontSize: 50,
    fontWeight: '900',
    color: Colors.navy
  },
  subtitle: {
    fontSize: 20,
    fontWeight: '600',
    color: Colors.subtle
  },
  input: {
    minHeight: 72,
    borderRadius: 16,
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    fontSize: 28,
    fontWeight: '700',
    borderWidth: 2,
    borderColor: '#CBD5E1'
  }
});
