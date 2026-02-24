import { expect } from "chai";
import { ethers } from "hardhat";
import { OpenMemoryPaymaster, EventfulDataEdge } from "../typechain-types";

describe("OpenMemoryPaymaster", function () {
  let paymaster: OpenMemoryPaymaster;
  let edge: EventfulDataEdge;
  let owner: any;
  let user: any;
  let mockEntryPoint: any;

  const MAX_OPS_PER_HOUR = 100;
  const RATE_LIMIT_WINDOW = 3600; // 1 hour in seconds

  beforeEach(async function () {
    [owner, user, mockEntryPoint] = await ethers.getSigners();

    // Deploy EventfulDataEdge
    const EdgeFactory = await ethers.getContractFactory("EventfulDataEdge");
    edge = await EdgeFactory.deploy(mockEntryPoint.address);
    await edge.waitForDeployment();

    // Deploy Paymaster
    const PaymasterFactory = await ethers.getContractFactory("OpenMemoryPaymaster");
    paymaster = await PaymasterFactory.deploy(
      mockEntryPoint.address,
      await edge.getAddress(),
      MAX_OPS_PER_HOUR,
      RATE_LIMIT_WINDOW
    );
    await paymaster.waitForDeployment();

    // Fund the paymaster (it needs ETH to sponsor gas)
    await owner.sendTransaction({
      to: await paymaster.getAddress(),
      value: ethers.parseEther("1.0"),
    });
  });

  describe("Deployment", function () {
    it("should set the correct entryPoint", async function () {
      expect(await paymaster.entryPoint()).to.equal(mockEntryPoint.address);
    });

    it("should set the correct dataEdge address", async function () {
      expect(await paymaster.dataEdge()).to.equal(await edge.getAddress());
    });

    it("should set rate limit parameters", async function () {
      expect(await paymaster.maxOpsPerWindow()).to.equal(MAX_OPS_PER_HOUR);
      expect(await paymaster.rateLimitWindow()).to.equal(RATE_LIMIT_WINDOW);
    });

    it("should set deployer as owner", async function () {
      expect(await paymaster.owner()).to.equal(owner.address);
    });

    it("should reject zero address for entryPoint", async function () {
      const Factory = await ethers.getContractFactory("OpenMemoryPaymaster");
      await expect(
        Factory.deploy(ethers.ZeroAddress, await edge.getAddress(), 100, 3600)
      ).to.be.revertedWith("Invalid entryPoint");
    });

    it("should reject zero address for dataEdge", async function () {
      const Factory = await ethers.getContractFactory("OpenMemoryPaymaster");
      await expect(
        Factory.deploy(mockEntryPoint.address, ethers.ZeroAddress, 100, 3600)
      ).to.be.revertedWith("Invalid dataEdge");
    });

    it("should reject zero maxOps", async function () {
      const Factory = await ethers.getContractFactory("OpenMemoryPaymaster");
      await expect(
        Factory.deploy(mockEntryPoint.address, await edge.getAddress(), 0, 3600)
      ).to.be.revertedWith("Invalid maxOps");
    });

    it("should reject zero window", async function () {
      const Factory = await ethers.getContractFactory("OpenMemoryPaymaster");
      await expect(
        Factory.deploy(mockEntryPoint.address, await edge.getAddress(), 100, 0)
      ).to.be.revertedWith("Invalid window");
    });
  });

  describe("Configuration", function () {
    it("should allow owner to update rate limits", async function () {
      await paymaster.setRateLimits(200, 7200);
      expect(await paymaster.maxOpsPerWindow()).to.equal(200);
      expect(await paymaster.rateLimitWindow()).to.equal(7200);
    });

    it("should emit RateLimitsUpdated event", async function () {
      await expect(paymaster.setRateLimits(200, 7200))
        .to.emit(paymaster, "RateLimitsUpdated")
        .withArgs(200, 7200);
    });

    it("should reject non-owner updating rate limits", async function () {
      await expect(
        paymaster.connect(user).setRateLimits(200, 7200)
      ).to.be.revertedWith("Only owner");
    });

    it("should reject zero maxOps in setRateLimits", async function () {
      await expect(
        paymaster.setRateLimits(0, 7200)
      ).to.be.revertedWith("Invalid maxOps");
    });

    it("should reject zero window in setRateLimits", async function () {
      await expect(
        paymaster.setRateLimits(200, 0)
      ).to.be.revertedWith("Invalid window");
    });

    it("should allow owner to update dataEdge address", async function () {
      const newAddr = ethers.Wallet.createRandom().address;
      await paymaster.setDataEdge(newAddr);
      expect(await paymaster.dataEdge()).to.equal(newAddr);
    });

    it("should emit DataEdgeUpdated event", async function () {
      const newAddr = ethers.Wallet.createRandom().address;
      await expect(paymaster.setDataEdge(newAddr))
        .to.emit(paymaster, "DataEdgeUpdated")
        .withArgs(newAddr);
    });

    it("should reject non-owner updating dataEdge", async function () {
      await expect(
        paymaster.connect(user).setDataEdge(user.address)
      ).to.be.revertedWith("Only owner");
    });

    it("should reject zero address for setDataEdge", async function () {
      await expect(
        paymaster.setDataEdge(ethers.ZeroAddress)
      ).to.be.revertedWith("Invalid dataEdge");
    });
  });

  describe("Ownership", function () {
    it("should allow owner to transfer ownership", async function () {
      await paymaster.transferOwnership(user.address);
      expect(await paymaster.owner()).to.equal(user.address);
    });

    it("should reject non-owner transferring ownership", async function () {
      await expect(
        paymaster.connect(user).transferOwnership(user.address)
      ).to.be.revertedWith("Only owner");
    });

    it("should reject zero address for transferOwnership", async function () {
      await expect(
        paymaster.transferOwnership(ethers.ZeroAddress)
      ).to.be.revertedWith("Invalid owner");
    });
  });

  describe("Funding", function () {
    it("should accept ETH deposits", async function () {
      const balance = await ethers.provider.getBalance(await paymaster.getAddress());
      expect(balance).to.equal(ethers.parseEther("1.0"));
    });

    it("should emit Funded event on deposit", async function () {
      await expect(
        owner.sendTransaction({
          to: await paymaster.getAddress(),
          value: ethers.parseEther("0.5"),
        })
      ).to.emit(paymaster, "Funded");
    });

    it("should allow owner to withdraw", async function () {
      const tx = await paymaster.withdraw(ethers.parseEther("0.5"));
      await tx.wait();
      const paymasterBalance = await ethers.provider.getBalance(await paymaster.getAddress());
      expect(paymasterBalance).to.equal(ethers.parseEther("0.5"));
    });

    it("should emit Withdrawn event", async function () {
      await expect(paymaster.withdraw(ethers.parseEther("0.5")))
        .to.emit(paymaster, "Withdrawn")
        .withArgs(owner.address, ethers.parseEther("0.5"));
    });

    it("should reject non-owner withdrawal", async function () {
      await expect(
        paymaster.connect(user).withdraw(ethers.parseEther("0.5"))
      ).to.be.revertedWith("Only owner");
    });

    it("should reject withdrawal exceeding balance", async function () {
      await expect(
        paymaster.withdraw(ethers.parseEther("2.0"))
      ).to.be.revertedWith("Insufficient balance");
    });
  });

  describe("Rate limiting", function () {
    it("should track operation count per sender as zero initially", async function () {
      const count = await paymaster.getOpsCount(user.address);
      expect(count).to.equal(0);
    });

    it("should validate operations from entryPoint", async function () {
      const edgeAddr = await edge.getAddress();
      // Call validateOperation from the mockEntryPoint
      const result = await paymaster.connect(mockEntryPoint).validateOperation.staticCall(
        user.address,
        edgeAddr
      );
      expect(result).to.equal(true);
    });

    it("should reject operations not from entryPoint", async function () {
      const edgeAddr = await edge.getAddress();
      await expect(
        paymaster.connect(user).validateOperation(user.address, edgeAddr)
      ).to.be.revertedWith("Only EntryPoint");
    });

    it("should reject operations targeting wrong contract", async function () {
      const wrongTarget = ethers.Wallet.createRandom().address;
      const result = await paymaster.connect(mockEntryPoint).validateOperation.staticCall(
        user.address,
        wrongTarget
      );
      expect(result).to.equal(false);
    });

    it("should increment ops count after validateOperation", async function () {
      const edgeAddr = await edge.getAddress();
      await paymaster.connect(mockEntryPoint).validateOperation(user.address, edgeAddr);
      const count = await paymaster.getOpsCount(user.address);
      expect(count).to.equal(1);
    });

    it("should emit OperationSponsored event", async function () {
      const edgeAddr = await edge.getAddress();
      await expect(
        paymaster.connect(mockEntryPoint).validateOperation(user.address, edgeAddr)
      ).to.emit(paymaster, "OperationSponsored")
        .withArgs(user.address, 1);
    });
  });
});
