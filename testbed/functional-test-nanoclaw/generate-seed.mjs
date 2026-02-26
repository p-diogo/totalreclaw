#!/usr/bin/env node
/**
 * Generate a 12-word recovery phrase for OpenMemory.
 *
 * This phrase is the ONLY way to access your encrypted memories.
 * It will also serve as your identity on the decentralized network
 * in a future release.
 *
 * Usage:
 *   node generate-seed.mjs
 *   node generate-seed.mjs --quiet   (phrase only, no explanation)
 */

import { generateMnemonic } from '@scure/bip39';
import { wordlist } from '@scure/bip39/wordlists/english.js';

const quiet = process.argv.includes('--quiet');
const mnemonic = generateMnemonic(wordlist);

if (quiet) {
  console.log(mnemonic);
  process.exit(0);
}

console.log('');
console.log('============================================================');
console.log('  Your OpenMemory Recovery Phrase');
console.log('============================================================');
console.log('');
console.log('  ' + mnemonic);
console.log('');
console.log('------------------------------------------------------------');
console.log('');
console.log('  This 12-word phrase is the ONLY way to access your');
console.log('  encrypted memories. The server never sees your data');
console.log('  in readable form — it cannot recover it for you.');
console.log('');
console.log('  If you lose this phrase, your memories are gone forever.');
console.log('  If you move to a new device or agent, this phrase is');
console.log('  how you restore everything.');
console.log('');
console.log('  Store it somewhere safe. Treat it like a master password');
console.log('  that can never be reset.');
console.log('');
console.log('------------------------------------------------------------');
console.log('');
console.log('  Add this to your .env file:');
console.log('');
console.log('  OPENMEMORY_MASTER_PASSWORD="' + mnemonic + '"');
console.log('');
console.log('============================================================');
