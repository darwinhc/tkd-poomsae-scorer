// The emulator is expected to run with an English device locale, so the app UI is in English.
describe('First run', () => {
  beforeAll(async () => {
    await device.launchApp({ delete: true, newInstance: true, permissions: { camera: 'YES' } });
  });

  it('sets up the judge, lands on match setup in local mode and accepts a pasted QR', async () => {
    await expect(element(by.id('judge-name-input'))).toBeVisible();
    await element(by.id('judge-name-input')).typeText('Judge 1');
    await element(by.id('judge-save-btn')).tap();

    await expect(element(by.id('red-name-input'))).toBeVisible();
    await expect(element(by.id('blue-name-input'))).toBeVisible();

    await element(by.id('connection-badge')).tap();
    await expect(element(by.id('qr-paste-input'))).toBeVisible();
    await element(by.id('qr-paste-input')).replaceText(
      '{"baseUrl":"http://192.168.1.20:8080","stationId":"station-01","bootstrapToken":"mock","protocolVersion":"v1","expiresAt":"2099-01-01T00:00:00.000Z"}'
    );
    await element(by.id('use-pasted-qr-btn')).tap();

    await expect(element(by.id('credential-prompt-input'))).toBeVisible();
    await element(by.id('credential-prompt-cancel-btn')).tap();

    await element(by.id('connection-back-btn')).tap();
    await expect(element(by.id('red-name-input'))).toBeVisible();
  });
});
