#!/usr/bin/env npx tsx
/**
 * Generate a BIP-39 12-word mnemonic for use as TOTALRECLAW_MASTER_PASSWORD.
 *
 * Usage: npx tsx generate-mnemonic.ts
 */
import { generateMnemonic } from '@scure/bip39';
import { wordlist } from '@scure/bip39/wordlists/english.js';

const mnemonic = generateMnemonic(wordlist, 128);
console.log('\n  Your TotalReclaw master mnemonic (12 words):\n');
console.log(`  ${mnemonic}\n`);
console.log('  WRITE THIS DOWN. If you lose it, your memories are unrecoverable.');
console.log('  Set it as TOTALRECLAW_MASTER_PASSWORD in your .env file.\n');
