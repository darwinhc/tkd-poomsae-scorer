// The emulator is expected to run with an English device locale; native alert buttons
// have no testID, so they are matched by their English text.
describe('Scoring flow', () => {
  beforeAll(async () => {
    await device.launchApp({ newInstance: true });
  });

  it('starts a match, scores, corrects, advances the round and finalizes', async () => {
    await element(by.id('red-name-input')).replaceText('Competitor A');
    await element(by.id('blue-name-input')).replaceText('Competitor B');
    await element(by.id('start-match-btn')).tap();

    await expect(element(by.id('red-minus-1'))).toBeVisible();
    await element(by.id('red-minus-1')).tap();
    await element(by.id('red-plus-1')).tap();
    await element(by.id('blue-minus-2')).tap();
    await element(by.id('next-presentation-btn')).tap();
    await expect(element(by.id('red-presentation-speed-plus'))).toBeVisible();
    await element(by.id('red-presentation-speed-plus')).tap();
    await element(by.id('blue-presentation-rhythm-minus')).tap();
    await element(by.id('back-technique-btn')).tap();

    await device.launchApp({ newInstance: true });
    await expect(element(by.id('red-minus-1'))).toBeVisible();
    await element(by.id('blue-plus-1')).tap();

    await element(by.id('next-presentation-btn')).tap();
    await element(by.id('next-round-btn')).tap();

    await element(by.id('reset-btn')).tap();
    await element(by.text('Cancel')).tap();

    await element(by.id('next-presentation-btn')).tap();
    await element(by.id('finalize-btn')).tap();
    await element(by.text('Yes, finish')).tap();

    await expect(element(by.id('summary-title'))).toBeVisible();
    await element(by.id('history-btn')).tap();
    await expect(element(by.id('history-title'))).toBeVisible();
  });
});
