import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Ionicons } from '@expo/vector-icons';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { appFacade } from '@/application/appFacade';
import { PrimaryButton } from '@/components/PrimaryButton';
import { ScreenContainer } from '@/components/ScreenContainer';
import { DEFAULT_STATION_ID, MIN_RETAINED_MATCHES } from '@/constants/defaults';
import { Colors } from '@/constants/colors';
import { t } from '@/i18n';
import { errorMessage } from '@/i18n/LocalizedError';

export default function SettingsScreen() {
  const [form, setForm] = useState({
    judgeName: '',
    actionValue1: '0.1',
    actionValue2: '0.3',
    defaultStationId: DEFAULT_STATION_ID,
    defaultRounds: '2',
    defaultStartingScore: '4',
    presentationCategoryStartScore: '2',
    retainedMatchesCount: '2'
  });

  const load = useCallback(async () => {
    const settings = await appFacade.getSettings();
    setForm({
      judgeName: settings.judgeName,
      actionValue1: String(settings.actionValue1),
      actionValue2: String(settings.actionValue2),
      defaultStationId: settings.defaultStationId,
      defaultRounds: String(settings.defaultRounds),
      presentationCategoryStartScore: String(settings.presentationCategoryStartScore),
      defaultStartingScore: String(settings.defaultStartingScore),
      retainedMatchesCount: String(settings.retainedMatchesCount)
    });
  }, []);

  useFocusEffect(
    useCallback(() => {
      load().catch(() => undefined);
      return undefined;
    }, [load])
  );

  const save = async () => {
    try {
      await appFacade.saveSettings({
        judgeName: form.judgeName,
        actionValue1: Number(form.actionValue1),
        actionValue2: Number(form.actionValue2),
        defaultStationId: form.defaultStationId.trim(),
        defaultRounds: Number(form.defaultRounds),
        presentationCategoryStartScore: Number(form.presentationCategoryStartScore),
        defaultStartingScore: Number(form.defaultStartingScore),
        retainedMatchesCount: Math.max(MIN_RETAINED_MATCHES, Number(form.retainedMatchesCount))
      });
      Alert.alert(t('settings.savedTitle'), t('settings.savedMessage'), [
        {
          text: t('common.ok'),
          onPress: () => router.back()
        }
      ]);
    } catch (error: any) {
      Alert.alert(t('common.error'), errorMessage(error));
    }
  };

  return (
    <ScreenContainer>
      <View style={styles.headerRow}>
        <Pressable testID="back-settings-btn" style={styles.backBtn} onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={26} color={Colors.navy} />
        </Pressable>
        <Text style={styles.title}>{t('settings.title')}</Text>
      </View>

      <View style={styles.block}>
        <Input label={t('settings.judgeName')} value={form.judgeName} onChange={(v) => setForm((f) => ({ ...f, judgeName: v }))} />
        <Input label={t('settings.shortDeduction')} value={form.actionValue1} onChange={(v) => setForm((f) => ({ ...f, actionValue1: v }))} />
        <Input label={t('settings.longDeduction')} value={form.actionValue2} onChange={(v) => setForm((f) => ({ ...f, actionValue2: v }))} />
        <Input label={t('settings.defaultStation')} value={form.defaultStationId} onChange={(v) => setForm((f) => ({ ...f, defaultStationId: v }))} />
        <Input label={t('settings.roundsPerMatch')} value={form.defaultRounds} onChange={(v) => setForm((f) => ({ ...f, defaultRounds: v }))} />
        <Input label={t('settings.techniqueStart')} value={form.defaultStartingScore} onChange={(v) => setForm((f) => ({ ...f, defaultStartingScore: v }))} />
        <Input
          label={t('settings.presentationStart')}
          value={form.presentationCategoryStartScore}
          onChange={(v) => setForm((f) => ({ ...f, presentationCategoryStartScore: v }))}
        />
        <Input
          label={t('settings.retention', { min: MIN_RETAINED_MATCHES })}
          value={form.retainedMatchesCount}
          onChange={(v) => setForm((f) => ({ ...f, retainedMatchesCount: v }))}
        />
      </View>

      <PrimaryButton testID="save-settings-btn" title={t('settings.save')} onPress={save} />
    </ScreenContainer>
  );
}

function Input({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <View style={{ gap: 4 }}>
      <Text style={{ fontWeight: '800', color: Colors.navy }}>{label}</Text>
      <TextInput value={value} onChangeText={onChange} style={styles.input} autoCapitalize="none" />
    </View>
  );
}

const styles = StyleSheet.create({
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10
  },
  backBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff'
  },
  title: {
    fontSize: 38,
    fontWeight: '900',
    color: Colors.navy
  },
  block: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 12,
    gap: 10
  },
  input: {
    minHeight: 52,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#CBD5E1',
    paddingHorizontal: 12,
    fontSize: 16,
    backgroundColor: '#F8FAFC'
  }
});
