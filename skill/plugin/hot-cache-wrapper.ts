/**
 * Hot cache wrapper for the plugin.
 *
 * Self-contained AES-256-GCM encrypted cache (same implementation as
 * client/src/cache/hot-cache.ts but without cross-package import).
 */

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export interface HotFact {
  id: string;
  text: string;
  importance: number;
}

interface CachePayload {
  hotFacts: HotFact[];
  factCount: number;
  lastSyncedBlock: number;
  smartAccountAddress: string;
}

const MAX_HOT_FACTS = 30;
const IV_LENGTH = 12;
const TAG_LENGTH = 16;

export class PluginHotCache {
  private hotFacts: HotFact[] = [];
  private factCount = 0;
  private lastSyncedBlock = 0;
  private smartAccountAddress = '';
  private key: Buffer;

  constructor(private cachePath: string, hexKey: string) {
    this.key = Buffer.from(hexKey, 'hex');
  }

  getHotFacts(): HotFact[] { return [...this.hotFacts]; }
  getFactCount(): number { return this.factCount; }
  getLastSyncedBlock(): number { return this.lastSyncedBlock; }
  getSmartAccountAddress(): string { return this.smartAccountAddress; }

  setHotFacts(facts: HotFact[]): void {
    const sorted = [...facts].sort((a, b) => b.importance - a.importance);
    this.hotFacts = sorted.slice(0, MAX_HOT_FACTS);
  }

  setFactCount(count: number): void { this.factCount = count; }
  setLastSyncedBlock(block: number): void { this.lastSyncedBlock = block; }
  setSmartAccountAddress(addr: string): void { this.smartAccountAddress = addr; }

  flush(): void {
    const payload: CachePayload = {
      hotFacts: this.hotFacts,
      factCount: this.factCount,
      lastSyncedBlock: this.lastSyncedBlock,
      smartAccountAddress: this.smartAccountAddress,
    };

    const plaintext = Buffer.from(JSON.stringify(payload), 'utf-8');
    const iv = crypto.randomBytes(IV_LENGTH);
    const cipher = crypto.createCipheriv('aes-256-gcm', this.key, iv);
    const encrypted = Buffer.concat([cipher.update(plaintext), cipher.final()]);
    const tag = cipher.getAuthTag();

    const output = Buffer.concat([iv, tag, encrypted]);

    const dir = path.dirname(this.cachePath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(this.cachePath, output);
  }

  load(): void {
    if (!fs.existsSync(this.cachePath)) return;

    try {
      const data = fs.readFileSync(this.cachePath);
      if (data.length < IV_LENGTH + TAG_LENGTH) return;

      const iv = data.subarray(0, IV_LENGTH);
      const tag = data.subarray(IV_LENGTH, IV_LENGTH + TAG_LENGTH);
      const ciphertext = data.subarray(IV_LENGTH + TAG_LENGTH);

      const decipher = crypto.createDecipheriv('aes-256-gcm', this.key, iv);
      decipher.setAuthTag(tag);
      const decrypted = Buffer.concat([decipher.update(ciphertext), decipher.final()]);

      const payload: CachePayload = JSON.parse(decrypted.toString('utf-8'));
      this.hotFacts = payload.hotFacts || [];
      this.factCount = payload.factCount || 0;
      this.lastSyncedBlock = payload.lastSyncedBlock || 0;
      this.smartAccountAddress = payload.smartAccountAddress || '';
    } catch {
      this.hotFacts = [];
      this.factCount = 0;
      this.lastSyncedBlock = 0;
      this.smartAccountAddress = '';
    }
  }
}
