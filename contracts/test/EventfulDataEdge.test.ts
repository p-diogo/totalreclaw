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
    edge = await Factory.deploy();
    await edge.waitForDeployment();
  });

  describe("Deployment", function () {
    it("should set the deployer as owner", async function () {
      expect(await edge.owner()).to.equal(owner.address);
    });
  });

  describe("Log emission via fallback", function () {
    it("should emit Log event with calldata", async function () {
      const testData = ethers.toUtf8Bytes("encrypted-protobuf-payload-here");
      const edgeAddress = await edge.getAddress();
      const tx = await owner.sendTransaction({
        to: edgeAddress,
        data: testData,
      });
      const receipt = await tx.wait();

      const logEvent = receipt!.logs.find(
        (log: any) => log.address.toLowerCase() === edgeAddress.toLowerCase()
      );
      expect(logEvent).to.not.be.undefined;
    });

    it("should allow any address to write (permissionless)", async function () {
      const testData = ethers.toUtf8Bytes("user-encrypted-payload");
      const edgeAddress = await edge.getAddress();
      const tx = await user.sendTransaction({
        to: edgeAddress,
        data: testData,
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
      expect(ethers.hexlify(logEvent!.args.data)).to.equal(
        ethers.hexlify(testData)
      );
    });

    it("should emit correct data bytes in Log event", async function () {
      const payload = ethers.randomBytes(128);
      const tx = await owner.sendTransaction({
        to: await edge.getAddress(),
        data: payload,
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
      expect(ethers.hexlify(logEvent!.args.data)).to.equal(ethers.hexlify(payload));
    });

    it("should handle empty calldata via receive()", async function () {
      const tx = await owner.sendTransaction({
        to: await edge.getAddress(),
        value: ethers.parseEther("0.01"),
      });
      const receipt = await tx.wait();
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
