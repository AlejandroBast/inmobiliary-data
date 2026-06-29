import { chromium } from 'playwright';
import { config } from '../config.js';

export async function launchBrowser() {
  return chromium.launch({
    headless: config.bot.headless,
    args: ['--disable-dev-shm-usage']
  });
}

export async function newContext(browser, sourceKey) {
  const contextOptions = {
    viewport: { width: 1365, height: 900 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36',
    locale: 'es-CO',
    timezoneId: 'America/Bogota'
  };

  if (sourceKey === 'facebook' && config.facebookStorageState) {
    contextOptions.storageState = config.facebookStorageState;
  }

  return browser.newContext(contextOptions);
}

export async function politeDelay(ms = config.bot.delayMs) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}
