import { defineConfig } from '@playwright/test';
import path from 'node:path';

if (!process.env.BROWSER_OUTPUT) throw new Error('Set BROWSER_OUTPUT to task-owned private staging');

export default defineConfig({
  testDir: './tests/browser',
  testMatch: 'interactive.spec.mjs',
  workers: 1,
  retries: 0,
  timeout: 45000,
  expect: { timeout: 15000 },
  outputDir: path.resolve(process.env.BROWSER_OUTPUT),
  reporter: 'line',
  use: {
    headless: true,
    viewport: { width: 1440, height: 1100 },
    deviceScaleFactor: 1,
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium', channel: 'chromium',
      launchOptions: { args: process.platform === 'darwin' ? ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'] : [] } } },
    { name: 'webkit', use: { browserName: 'webkit', launchOptions: { executablePath: process.env.WEBKIT_EXECUTABLE } } },
  ],
});
