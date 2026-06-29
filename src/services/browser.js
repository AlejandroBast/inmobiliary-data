import { chromium } from 'playwright';
import { config } from '../config.js';

export async function launchBrowser() {
  const launchOptions = {
    headless: config.bot.headless,
    args: ['--disable-dev-shm-usage']
  };

  if (config.bot.browserExecutable) {
    launchOptions.executablePath = config.bot.browserExecutable;
  } else if (config.bot.browserChannel) {
    launchOptions.channel = config.bot.browserChannel;
  }

  return chromium.launch(launchOptions);
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

  const context = await browser.newContext(contextOptions);

  if (config.bot.blockHeavyResources && !config.bot.downloadImages) {
    await context.route('**/*', (route) => {
      const type = route.request().resourceType();
      if (['image', 'media', 'font'].includes(type)) {
        return route.abort();
      }
      return route.continue();
    });
  }

  return context;
}

export async function politeDelay(ms = config.bot.delayMs) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}
