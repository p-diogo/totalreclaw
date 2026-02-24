import { expect } from "chai";
import { ethers } from "hardhat";
import { EventfulDataEdge } from "../typechain-types";

describe("EventfulDataEdge", function () {
  let edge: EventfulDataEdge;
  let owner: any;
  let user: any;

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("EventfulDataEdge");
    // Deploy with owner as the "entryPoint" for testing
    edge = await Factory.deploy(owner.address);
    await edge.waitForDeployment();
  });

  describe("Deployment", function () {
    it("should set the entryPoint address", async function () {
      expect(await edge.entryPoint()).to.equal(owner.address);
    });

    it("should set the deployer as owner", async function () {
      expect(await edge.owner()).to.equal(owner.address);
    });

    it("should reject zero address as entryPoint", async function () {
      const Factory = await ethers.getContractFactory("EventfulDataEdge");
      await expect(
        Factory.deploy(ethers.ZeroAddress)
      ).to.be.revertedWith("Invalid entryPoint");
    });
  });

  describe("Log emission via fallback", function () {
    it("should emit Log event with calldata when called by entryPoint", async function () {
      const testData = ethers.toUtf8Bytes("encrypted-protobuf-payload-here");
      const edgeAddress = await edge.getAddress();
      const tx = await owner.sendTransaction({
        to: edgeAddress,
        data: testData,
      });
      const receipt = await tx.wait();

      // Verify Log event was emitted
      const logEvent = receipt!.logs.find(
        (log: any) => log.address.toLowerCase() === edgeAddress.toLowerCase()
      );
      expect(logEvent).to.not.be.undefined;
    });

    it("should revert when called by non-entryPoint address", async function () {
      const testData = ethers.toUtf8Bytes("should-fail");
      await expect(
        user.sendTransaction({
          to: await edge.getAddress(),
          data: testData,
        })
      ).to.be.revertedWith("Only EntryPoint");
    });

    it("should emit correct data bytes in Log event", async function () {
      // Simulate a realistic encrypted protobuf payload (128 bytes)
      const payload = ethers.randomBytes(128);
      const tx = await owner.sendTransaction({
        to: await edge.getAddress(),
        data: payload,
      });
      const receipt = await tx.wait();

      // Parse the Log event
      const iface = edge.interface;
      const parsedLogs = receipt!.logs
        .map((log: any) => {
          try { return iface.parseLog({ topics: log.topics, data: log.data }); }
          catch { return null; }
        })
        .filter((l: any) => l !== null);

      const logEvent = parsedLogs.find((l: any) => l?.name === "Log");
      expect(logEvent).to.not.be.undefined;
      expect(ethers.hexlify(logEvent!.args.data)).to.equal(ethers.hexlify(payload));
    });

    it("should handle empty calldata via receive()", async function () {
      // Sending ETH with no data triggers receive(), which is a no-op
      const tx = await owner.sendTransaction({
        to: await edge.getAddress(),
        value: ethers.parseEther("0.01"),
      });
      const receipt = await tx.wait();
      // receive() does not emit events — just accepts ETH
      expect(receipt!.status).to.equal(1);
    });

    it("should handle large payloads (1KB)", async function () {
      const largePayload = ethers.randomBytes(1024);
      const tx = await owner.sendTransaction({
        to: await edge.getAddress(),
        data: largePayload,
      });
      const receipt = await tx.wait();

      const iface = edge.interface;
      const parsedLogs = receipt!.logs
        .map((log: any) => {
          try { return iface.parseLog({ topics: log.topics, data: log.data }); }
          catch { return null; }
        })
        .filter((l: any) => l !== null);

      const logEvent = parsedLogs.find((l: any) => l?.name === "Log");
      expect(logEvent).to.not.be.undefined;
      expect(logEvent!.args.data.length).to.be.greaterThan(0);
    });
  });

  describe("Owner functions", function () {
    it("should allow owner to update entryPoint", async function () {
      await edge.setEntryPoint(user.address);
      expect(await edge.entryPoint()).to.equal(user.address);
    });

    it("should reject non-owner updating entryPoint", async function () {
      await expect(
        edge.connect(user).setEntryPoint(user.address)
      ).to.be.revertedWith("Only owner");
    });

    it("should reject zero address for setEntryPoint", async function () {
      await expect(
        edge.setEntryPoint(ethers.ZeroAddress)
      ).to.be.revertedWith("Invalid entryPoint");
    });

    it("should allow owner to transfer ownership", async function () {
      await edge.transferOwnership(user.address);
      expect(await edge.owner()).to.equal(user.address);
    });

    it("should reject non-owner transferring ownership", async function () {
      await expect(
        edge.connect(user).transferOwnership(user.address)
      ).to.be.revertedWith("Only owner");
    });

    it("should reject zero address for transferOwnership", async function () {
      await expect(
        edge.transferOwnership(ethers.ZeroAddress)
      ).to.be.revertedWith("Invalid owner");
    });
  });
});
