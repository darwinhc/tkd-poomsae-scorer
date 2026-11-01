import type { DetoxConfig } from 'detox';

const config: DetoxConfig = {
  testRunner: {
    args: {
      $0: 'jest',
      config: 'tests/e2e/jest.e2e.config.js'
    },
    jest: {
      setupTimeout: 120000
    }
  },
  apps: {
    'android.debug': {
      type: 'android.apk',
      binaryPath: 'android/app/build/outputs/apk/debug/app-debug.apk',
      build: 'cd android && ./gradlew assembleDebug assembleAndroidTest -DtestBuildType=debug'
    }
  },
  devices: {
    emulator: {
      type: 'android.emulator',
      device: {
        avdName: 'Pixel_7_API_35'
      }
    }
  },
  configurations: {
    'android.emu.debug': {
      device: 'emulator',
      app: 'android.debug'
    }
  }
};

export default config;
