import {
  generateMnemonic,
  mnemonicToKeys,
  mnemonicToSmartAccountAddress,
  validateMnemonic,
  DERIVATION_PATH,
} from "../src/crypto/seed";

describe("Seed Module", () => {
  // Known test vector — DO NOT use this mnemonic for real funds
  const TEST_MNEMONIC =
    "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about";

  describe("generateMnemonic", () => {
    it("should generate a 12-word mnemonic", () => {
      const mnemonic = generateMnemonic();
      const words = mnemonic.split(" ");
      expect(words).toHaveLength(12);
    });

    it("should generate valid BIP-39 mnemonics", () => {
      const mnemonic = generateMnemonic();
      expect(validateMnemonic(mnemonic)).toBe(true);
    });

    it("should generate unique mnemonics each time", () => {
      const m1 = generateMnemonic();
      const m2 = generateMnemonic();
      expect(m1).not.toEqual(m2);
    });
  });

  describe("validateMnemonic", () => {
    it("should accept valid 12-word mnemonic", () => {
      expect(validateMnemonic(TEST_MNEMONIC)).toBe(true);
    });

    it("should reject invalid mnemonic", () => {
      expect(validateMnemonic("not a valid mnemonic phrase at all")).toBe(false);
    });

    it("should reject empty string", () => {
      expect(validateMnemonic("")).toBe(false);
    });

    it("should reject null-ish values", () => {
      expect(validateMnemonic("   ")).toBe(false);
    });
  });

  describe("mnemonicToKeys", () => {
    it("should derive encryption key (32 bytes)", async () => {
      const keys = await mnemonicToKeys(TEST_MNEMONIC);
      expect(keys.encryptionKey).toBeInstanceOf(Buffer);
      expect(keys.encryptionKey.length).toBe(32);
    });

    it("should derive auth key (32 bytes)", async () => {
      const keys = await mnemonicToKeys(TEST_MNEMONIC);
      expect(keys.authKey).toBeInstanceOf(Buffer);
      expect(keys.authKey.length).toBe(32);
    });

    it("should derive a private key (32 bytes)", async () => {
      const keys = await mnemonicToKeys(TEST_MNEMONIC);
      expect(keys.privateKey).toBeInstanceOf(Buffer);
      expect(keys.privateKey.length).toBe(32);
    });

    it("should derive an EOA address (20 bytes hex)", async () => {
      const keys = await mnemonicToKeys(TEST_MNEMONIC);
      expect(keys.eoaAddress).toMatch(/^0x[0-9a-fA-F]{40}$/);
    });

    it("should be deterministic (same mnemonic = same keys)", async () => {
      const keys1 = await mnemonicToKeys(TEST_MNEMONIC);
      const keys2 = await mnemonicToKeys(TEST_MNEMONIC);
      expect(keys1.encryptionKey.equals(keys2.encryptionKey)).toBe(true);
      expect(keys1.authKey.equals(keys2.authKey)).toBe(true);
      expect(keys1.privateKey.equals(keys2.privateKey)).toBe(true);
      expect(keys1.eoaAddress).toEqual(keys2.eoaAddress);
    });

    it("should derive different keys for different mnemonics", async () => {
      const m2 = "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong";
      const keys1 = await mnemonicToKeys(TEST_MNEMONIC);
      const keys2 = await mnemonicToKeys(m2);
      expect(keys1.encryptionKey.equals(keys2.encryptionKey)).toBe(false);
    });

    it("should derive different encryption and auth keys", async () => {
      const keys = await mnemonicToKeys(TEST_MNEMONIC);
      expect(keys.encryptionKey.equals(keys.authKey)).toBe(false);
    });

    it("should throw for invalid mnemonic", async () => {
      await expect(mnemonicToKeys("invalid mnemonic")).rejects.toThrow(
        "Invalid BIP-39 mnemonic"
      );
    });
  });

  describe("mnemonicToSmartAccountAddress", () => {
    it("should return a valid Ethereum address", async () => {
      const addr = await mnemonicToSmartAccountAddress(TEST_MNEMONIC);
      expect(addr).toMatch(/^0x[0-9a-fA-F]{40}$/);
    });

    it("should be deterministic", async () => {
      const a1 = await mnemonicToSmartAccountAddress(TEST_MNEMONIC);
      const a2 = await mnemonicToSmartAccountAddress(TEST_MNEMONIC);
      expect(a1).toEqual(a2);
    });

    it("should return different addresses for different mnemonics", async () => {
      const a1 = await mnemonicToSmartAccountAddress(TEST_MNEMONIC);
      const m2 = "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong";
      const a2 = await mnemonicToSmartAccountAddress(m2);
      expect(a1).not.toEqual(a2);
    });
  });

  describe("DERIVATION_PATH", () => {
    it("should be standard Ethereum path", () => {
      expect(DERIVATION_PATH).toBe("m/44'/60'/0'/0/0");
    });
  });
});
