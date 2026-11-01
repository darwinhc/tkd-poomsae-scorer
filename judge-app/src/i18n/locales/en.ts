/**
 * English UI strings (default and fallback language).
 * Every key defined here must also exist in `es.ts`.
 * Placeholders use the `{name}` syntax and are filled by `t(key, params)`.
 */
export const en = {
  // Common
  'common.error': 'Error',
  'common.ok': 'OK',
  'common.cancel': 'Cancel',
  'common.no': 'No',
  'common.back': 'Back',
  'common.continue': 'Continue',
  'common.saving': 'Saving...',
  'common.loading': 'Loading...',
  'common.reset': 'Reset',
  'common.total': 'Total',
  'common.technique': 'Technique',
  'common.presentation': 'Presentation',
  'common.red': 'Red',
  'common.blue': 'Blue',
  'common.redUpper': 'RED',
  'common.blueUpper': 'BLUE',
  'common.left': 'left',
  'common.right': 'right',
  'common.localMode': 'Local mode',
  'common.versus': '{left} vs {right}',

  // Connection status badges
  'status.connected': 'Connected',
  'status.reconnecting': 'Reconnecting',
  'status.notConnected': 'Not connected',

  // Match lifecycle statuses
  'matchStatus.active': 'Active',
  'matchStatus.closed': 'Closed',
  'matchStatus.pending': 'Pending',
  'matchStatus.closedPending': 'Closed, pending',
  'matchStatus.finalized': 'Finalized',
  'matchStatus.retrying': 'Retrying',

  // Close match confirmation (technical scoring and presentation screens)
  'closeMatch.title': 'Close match',
  'closeMatch.message': 'Are you sure you want to close this match?',
  'closeMatch.confirm': 'Yes, close',

  // Judge setup screen
  'judgeSetup.title': 'JUDGE',
  'judgeSetup.subtitle': 'Operator name',
  'judgeSetup.namePlaceholder': 'e.g. Judge 1',
  'judgeSetup.nameRequiredTitle': 'Name required',
  'judgeSetup.nameRequiredMessage': 'Enter at least 2 letters',

  // Connection screen
  'connection.title': 'Connection',
  'connection.judgePlaceholder': 'Judge',
  'connection.qrCode': 'QR code',
  'connection.scanQr': 'Scan QR',
  'connection.closeCamera': 'Close camera',
  'connection.cameraPermissionRequired': 'Camera permission required',
  'connection.pasteQrPlaceholder': 'Paste QR JSON',
  'connection.usePastedQr': 'Use pasted QR',
  'connection.credentialPlaceholder': 'PIN / password',
  'connection.signIn': 'Sign in',
  'connection.signingIn': 'Signing in...',
  'connection.connecting': 'Connecting...',
  'connection.disconnect': 'Disconnect',
  'connection.disconnectMessage': 'Leave the connected area?',
  'connection.disconnectConfirm': 'Yes, disconnect',
  'connection.stationPasswordTitle': 'Station password',
  'connection.warningTitle': 'Warning',
  'connection.qrStationNotActive': 'The QR station ({stationId}) is not listed as active.',
  'connection.invalidQrTitle': 'Invalid QR',
  'connection.missingDataTitle': 'Missing data',
  'connection.missingDataMessage': 'Enter station and password',
  'connection.signInFailedTitle': 'Could not sign in',

  // Match setup screen
  'matchSetup.title': 'Match',
  'matchSetup.activeMatch': 'Active match',
  'matchSetup.activeMatchWithId': 'Active match · {matchId}',
  'matchSetup.noActiveMatch': 'No active match',
  'matchSetup.sync': 'Sync',
  'matchSetup.syncing': 'Syncing...',
  'matchSetup.syncErrorTitle': 'Sync',
  'matchSetup.swapSides': 'Swap sides',
  'matchSetup.redSideLabel': 'RED ({side})',
  'matchSetup.blueSideLabel': 'BLUE ({side})',
  'matchSetup.note': 'Rounds and scores: Settings or server update.',
  'matchSetup.settings': 'Settings',
  'matchSetup.start': 'Start',
  'matchSetup.starting': 'Starting...',
  'matchSetup.missingNames': 'Missing names',

  // Technical scoring screen
  'technicalScoring.noActiveMatch': 'No active match',
  'technicalScoring.setUpMatch': 'Set up match',
  'technicalScoring.resetTitle': 'Reset technique',
  'technicalScoring.resetMessage': "Clear this round's technique score?",

  // Presentation screen
  'presentation.noActiveMatch': 'No active match',
  'presentation.backToTechnique': 'Back to technique',
  'presentation.resetTitle': 'Reset presentation',
  'presentation.resetMessage': "Clear only this round's presentation score?",
  'presentation.resetConfirm': 'Yes, reset',
  'presentation.finish': 'Finish',
  'presentation.finishTitle': 'Finish match',
  'presentation.finishMessage': 'Close the match?',
  'presentation.finishConfirm': 'Yes, finish',
  'presentation.notAllowedTitle': 'Not allowed',
  'presentation.lastRoundMessage': 'You are already in the last round',
  'presentation.speedPower': 'Speed and power',
  'presentation.speedPowerShort': 'Speed/Power',
  'presentation.rhythmTempo': 'Rhythm and tempo',
  'presentation.energyExpression': 'Expression of energy',

  // Summary screen
  'summary.title': 'SUMMARY',
  'summary.noData': 'No data',
  'summary.goToScoring': 'Go to scoring',
  'summary.redTotal': 'Red {total}',
  'summary.blueTotal': 'Blue {total}',
  'summary.rounds': 'Rounds',
  'summary.roundTitle': 'Round {number}',
  'summary.station': 'Station: {name}',
  'summary.noStation': 'No station',
  'summary.server': 'Server: {status}',
  'summary.waitingNewMatch': 'Waiting for a new match',
  'summary.restart': 'Restart',
  'summary.sendNow': 'Send now',
  'summary.syncStarted': 'Sync started',
  'summary.syncFailed': 'Could not sync',
  'summary.history': 'History',

  // History screen
  'history.title': 'HISTORY',
  'history.sectionActive': 'Active',
  'history.sectionPending': 'Pending',
  'history.sectionFinalized': 'Finalized',

  // Settings screen
  'settings.title': 'SETTINGS',
  'settings.judgeName': 'Judge name',
  'settings.shortDeduction': 'Short deduction',
  'settings.longDeduction': 'Long deduction',
  'settings.defaultStation': 'Default station',
  'settings.roundsPerMatch': 'Rounds per match',
  'settings.techniqueStart': 'Technique starting score',
  'settings.presentationStart': 'Starting score per presentation bar',
  'settings.retention': 'Retention (min {min})',
  'settings.save': 'Save',
  'settings.savedTitle': 'Saved',
  'settings.savedMessage': 'Settings updated',

  // Errors raised by services and shown to the user
  'errors.networkLocalhost':
    'Network error: "localhost" does not work from the phone. Use the server LAN IP (e.g. http://192.168.1.20:8080).',
  'errors.networkLocalHttps':
    'Network error: local HTTPS may fail because the certificate is not trusted on the phone. Use LAN HTTP or a valid certificate.',
  'errors.networkGeneric': 'Network error: check the server URL/IP/port. Base URL: {baseUrl}.',
  'errors.networkGenericWithDetail': 'Network error: check the server URL/IP/port. Base URL: {baseUrl}. Detail: {detail}',
  'errors.loadStationsFailed': 'Could not load stations ({status})',
  'errors.readActiveMatchFailed': 'Could not read the active match ({status})',
  'errors.connectionRejected': 'Connection rejected ({status})',
  'errors.connectionRejectedWithDetail': 'Connection rejected ({status}): {detail}',
  'errors.scoreEventSyncFailed': 'Score event sync failed ({status})',
  'errors.finalizeFailed': 'Finalize failed ({status})',
  'errors.credentialRequired': 'Credential required',
  'errors.finalizeMatchIdRequired': 'Invalid finalize payload: matchId is required and cannot be empty',
  'errors.saveServerFirst': 'Save a server first',
  'errors.serverNotConfigured': 'Server not configured',
  'errors.judgeNameRequired': 'Judge name required',
  'errors.noActiveMatch': 'No active match',
  'errors.noActiveStationSession': 'No active station session',
  'errors.matchNotActive': 'The match is not active',
  'errors.cannotAdvance': 'Cannot advance',
  'errors.cannotAdvanceRound': 'Cannot advance to the next round',
  'errors.sessionRequiredToFinalize': 'An active session is required to finalize',
  'errors.summaryBuildFailed': 'Could not build the summary',
  'errors.noServerActiveMatch': 'There is no active match on the server. Sync and try again.',
  'errors.qrLocalhost': 'The QR uses localhost. On a phone you must use the server LAN IP (e.g. http://192.168.1.20:8080).',
  'errors.qrExpired': 'QR expired'
} as const;

export type TranslationKey = keyof typeof en;
