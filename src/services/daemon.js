import { config } from '../config.js';
import { logger } from '../logger.js';
import { scanSources } from './scanner.js';

export class ScannerDaemon {
  constructor() {
    this.enabled = false;
    this.running = false;
    this.timer = null;
    this.startedAt = null;
    this.lastRunStartedAt = null;
    this.lastRunFinishedAt = null;
    this.nextRunAt = null;
    this.lastSummaries = [];
    this.lastError = null;
    this.runCount = 0;
  }

  start({ runImmediately = false } = {}) {
    if (this.enabled) return this.getStatus();
    this.enabled = true;
    this.startedAt = new Date();
    this.scheduleNext(runImmediately ? 0 : this.intervalMs);
    logger.info({ intervalMinutes: config.bot.scanIntervalMinutes }, 'Daemon de escaneo iniciado');
    return this.getStatus();
  }

  stop() {
    this.enabled = false;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.nextRunAt = null;
    logger.info('Daemon de escaneo detenido');
    return this.getStatus();
  }

  async runNow({ reason = 'manual' } = {}) {
    if (this.running) {
      return {
        skipped: true,
        reason: 'Ya hay un escaneo en proceso',
        status: this.getStatus()
      };
    }
    await this.executeCycle(reason);
    return {
      skipped: false,
      status: this.getStatus()
    };
  }

  triggerRunNow({ reason = 'manual' } = {}) {
    if (this.running) {
      return {
        skipped: true,
        reason: 'Ya hay un escaneo en proceso',
        status: this.getStatus()
      };
    }
    setTimeout(() => {
      this.executeCycle(reason).catch((error) => {
        logger.error({ error: error.message }, 'Fallo no controlado al disparar escaneo');
      });
    }, 0);
    return {
      skipped: false,
      queued: true,
      status: this.getStatus()
    };
  }

  scheduleNext(delayMs) {
    if (!this.enabled) return;
    if (this.timer) clearTimeout(this.timer);
    const safeDelay = Math.max(0, delayMs);
    this.nextRunAt = new Date(Date.now() + safeDelay);
    this.timer = setTimeout(() => {
      this.executeCycle('programado').catch((error) => {
        logger.error({ error: error.message }, 'Fallo no controlado en ciclo programado');
      });
    }, safeDelay);
  }

  async executeCycle(reason) {
    if (this.running) return;
    this.running = true;
    this.lastRunStartedAt = new Date();
    this.lastError = null;
    this.nextRunAt = null;

    try {
      logger.info({ reason }, 'Iniciando escaneo automatico de todas las fuentes');
      this.lastSummaries = await scanSources({ all: true });
      this.runCount += 1;
      this.lastRunFinishedAt = new Date();
      logger.info({ summaries: this.lastSummaries }, 'Escaneo automatico finalizado');
    } catch (error) {
      this.lastError = error.message;
      this.lastRunFinishedAt = new Date();
      logger.error({ error: error.message }, 'Escaneo automatico fallo');
    } finally {
      this.running = false;
      if (this.enabled) this.scheduleNext(this.intervalMs);
    }
  }

  get intervalMs() {
    return Math.max(1, config.bot.scanIntervalMinutes) * 60 * 1000;
  }

  getStatus() {
    return {
      enabled: this.enabled,
      running: this.running,
      intervalMinutes: config.bot.scanIntervalMinutes,
      startedAt: this.startedAt,
      lastRunStartedAt: this.lastRunStartedAt,
      lastRunFinishedAt: this.lastRunFinishedAt,
      nextRunAt: this.nextRunAt,
      runCount: this.runCount,
      lastError: this.lastError,
      lastSummaries: this.lastSummaries,
      scanMode: {
        allSources: true,
        maxPages: config.bot.maxPages,
        maxListingsPerSource: config.bot.maxListingsPerSource,
        unlimitedPages: config.bot.maxPages <= 0,
        unlimitedListings: config.bot.maxListingsPerSource <= 0,
        scanConcurrency: config.bot.scanConcurrency,
        skipKnownUrls: config.bot.skipKnownUrls,
        downloadImages: config.bot.downloadImages,
        saveEvidence: config.bot.saveEvidence,
        city: config.bot.city,
        department: config.bot.department,
        onlySales: true
      }
    };
  }
}

export const scannerDaemon = new ScannerDaemon();
