import {
  buildUserOperation,
  encodeFactAsCalldata,
  UserOperationConfig,
} from "../src/userop/builder";

describe("UserOperation Builder", () => {
  // Deterministic test key (not a real key -- DO NOT use for real funds)
  const TEST_PRIVATE_KEY = Buffer.alloc(32, 0x01);
  const TEST_EDGE_ADDRESS = "0xababababababababababababababababababababab" as `0x${string}`;
  const TEST_ENTRY_POINT = "0x0000000071727De22E5E9d8BAf0edAc6f37da032" as `0x${string}`;

  describe("encodeFactAsCalldata", () => {
    it("should encode encrypted blob as hex calldata", () => {
      const encryptedBlob = Buffer.from("test-encrypted-payload");
      const calldata = encodeFactAsCalldata(encryptedBlob);

      expect(calldata).toMatch(/^0x[0-9a-f]+$/);
      // Calldata should contain the raw encrypted bytes
      expect(calldata).toBe("0x" + encryptedBlob.toString("hex"));
    });

    it("should handle empty payload", () => {
      const calldata = encodeFactAsCalldata(Buffer.alloc(0));
      expect(calldata).toBe("0x");
    });

    it("should handle large payloads (1KB)", () => {
      const largePayload = Buffer.alloc(1024, 0xff);
      const calldata = encodeFactAsCalldata(largePayload);
      expect(calldata.length).toBe(2 + 1024 * 2); // 0x + hex chars
    });

    it("should correctly encode known bytes", () => {
      const payload = Buffer.from([0xde, 0xad, 0xbe, 0xef]);
      const calldata = encodeFactAsCalldata(payload);
      expect(calldata).toBe("0xdeadbeef");
    });
  });

  describe("buildUserOperation", () => {
    it("should create a valid UserOperation structure", async () => {
      const encryptedBlob = Buffer.from("encrypted-protobuf-fact");

      const config: UserOperationConfig = {
        privateKey: TEST_PRIVATE_KEY,
        dataEdgeAddress: TEST_EDGE_ADDRESS,
        entryPointAddress: TEST_ENTRY_POINT,
        chainId: 84532, // Base Sepolia
        encryptedPayload: encryptedBlob,
      };

      const userOp = await buildUserOperation(config);

      expect(userOp).toBeDefined();
      expect(userOp.callData).toBe("0x" + encryptedBlob.toString("hex"));
      expect(userOp.target).toBe(TEST_EDGE_ADDRESS);
    });

    it("should set correct nonce (0 for first operation)", async () => {
      const config: UserOperationConfig = {
        privateKey: TEST_PRIVATE_KEY,
        dataEdgeAddress: TEST_EDGE_ADDRESS,
        entryPointAddress: TEST_ENTRY_POINT,
        chainId: 84532,
        encryptedPayload: Buffer.from("test"),
      };

      const userOp = await buildUserOperation(config);
      expect(userOp.nonce).toBe(0n);
    });

    it("should use provided nonce when specified", async () => {
      const config: UserOperationConfig = {
        privateKey: TEST_PRIVATE_KEY,
        dataEdgeAddress: TEST_EDGE_ADDRESS,
        entryPointAddress: TEST_ENTRY_POINT,
        chainId: 84532,
        encryptedPayload: Buffer.from("test"),
        nonce: 42n,
      };

      const userOp = await buildUserOperation(config);
      expect(userOp.nonce).toBe(42n);
    });

    it("should include a valid signature", async () => {
      const config: UserOperationConfig = {
        privateKey: TEST_PRIVATE_KEY,
        dataEdgeAddress: TEST_EDGE_ADDRESS,
        entryPointAddress: TEST_ENTRY_POINT,
        chainId: 84532,
        encryptedPayload: Buffer.from("test"),
      };

      const userOp = await buildUserOperation(config);
      expect(userOp.userOpJson.signature).toBeDefined();
      expect(typeof userOp.userOpJson.signature).toBe("string");
      expect((userOp.userOpJson.signature as string).startsWith("0x")).toBe(true);
      // Signature should not be empty placeholder
      expect(userOp.userOpJson.signature).not.toBe("0x");
    });

    it("should produce a valid sender address", async () => {
      const config: UserOperationConfig = {
        privateKey: TEST_PRIVATE_KEY,
        dataEdgeAddress: TEST_EDGE_ADDRESS,
        entryPointAddress: TEST_ENTRY_POINT,
        chainId: 84532,
        encryptedPayload: Buffer.from("test"),
      };

      const userOp = await buildUserOperation(config);
      expect(userOp.sender).toMatch(/^0x[0-9a-fA-F]{40}$/);
    });

    it("should be deterministic (same input = same output)", async () => {
      const config: UserOperationConfig = {
        privateKey: TEST_PRIVATE_KEY,
        dataEdgeAddress: TEST_EDGE_ADDRESS,
        entryPointAddress: TEST_ENTRY_POINT,
        chainId: 84532,
        encryptedPayload: Buffer.from("test"),
      };

      const userOp1 = await buildUserOperation(config);
      const userOp2 = await buildUserOperation(config);

      expect(userOp1.callData).toBe(userOp2.callData);
      expect(userOp1.sender).toBe(userOp2.sender);
      expect(userOp1.target).toBe(userOp2.target);
    });

    it("should include all required ERC-4337 fields in userOpJson", async () => {
      const config: UserOperationConfig = {
        privateKey: TEST_PRIVATE_KEY,
        dataEdgeAddress: TEST_EDGE_ADDRESS,
        entryPointAddress: TEST_ENTRY_POINT,
        chainId: 84532,
        encryptedPayload: Buffer.from("test"),
      };

      const userOp = await buildUserOperation(config);
      const json = userOp.userOpJson;

      expect(json).toHaveProperty("sender");
      expect(json).toHaveProperty("nonce");
      expect(json).toHaveProperty("initCode");
      expect(json).toHaveProperty("callData");
      expect(json).toHaveProperty("callGasLimit");
      expect(json).toHaveProperty("verificationGasLimit");
      expect(json).toHaveProperty("preVerificationGas");
      expect(json).toHaveProperty("maxFeePerGas");
      expect(json).toHaveProperty("maxPriorityFeePerGas");
      expect(json).toHaveProperty("paymasterAndData");
      expect(json).toHaveProperty("signature");
    });
  });
});
