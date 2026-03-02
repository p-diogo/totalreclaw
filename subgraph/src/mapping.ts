/**
 * Subgraph mapping for EventfulDataEdge.
 *
 * Handles Log(bytes) events emitted by the EventfulDataEdge contract.
 * Each event contains an encrypted Protobuf-serialized TotalReclawFact.
 * The mapping extracts metadata fields and stores them as FactEntity records.
 *
 * IMPORTANT: The subgraph stores encrypted data. It never sees plaintext.
 * The blind_indices are SHA-256 hashes — the subgraph can match them but
 * cannot reverse them to learn the original content.
 */

import { BigDecimal, BigInt, Bytes } from "@graphprotocol/graph-ts";
import { Log } from "../generated/EventfulDataEdge/EventfulDataEdge";
import { FactEntity, GlobalState } from "../generated/schema";
import { decodeFact } from "./protobuf";

const GLOBAL_STATE_ID = "global";

function getOrCreateGlobalState(): GlobalState {
  let state = GlobalState.load(GLOBAL_STATE_ID);
  if (state == null) {
    state = new GlobalState(GLOBAL_STATE_ID);
    state.nextSequenceId = BigInt.fromI32(1);
    state.totalFacts = BigInt.zero();
    state.lastUpdated = BigInt.zero();
  }
  return state;
}

export function handleLog(event: Log): void {
  let rawData = event.params.data;

  // Attempt to decode the Protobuf payload
  let decoded = decodeFact(rawData);

  // Use the decoded ID if available, otherwise generate from tx hash + log index
  let factId = decoded.id;
  if (factId == "") {
    factId = event.transaction.hash.toHexString() + "-" + event.logIndex.toString();
  }

  // Load or create the FactEntity
  let entity = FactEntity.load(factId);
  let isNew = entity == null;

  if (isNew) {
    entity = new FactEntity(factId);
  }

  // The owner is the Smart Account address (tx.from for ERC-4337)
  // In ERC-4337, tx.from is the bundler, but the sender is in the UserOp.
  // For the subgraph, we use the address extracted from the Protobuf payload.
  // If not present, fall back to tx.from (works for direct calls in testing).
  if (decoded.owner != "") {
    entity!.owner = Bytes.fromHexString(decoded.owner);
  } else {
    entity!.owner = event.transaction.from;
  }

  entity!.encryptedBlob = rawData; // Store the full raw event data
  entity!.blindIndices = decoded.blindIndices;
  entity!.decayScore = decoded.decayScore;
  entity!.isActive = decoded.isActive;
  entity!.timestamp = event.block.timestamp;
  entity!.blockNumber = event.block.number;
  entity!.txHash = event.transaction.hash;
  entity!.contentFp = decoded.contentFp;
  entity!.agentId = decoded.agentId;
  entity!.version = decoded.version;
  entity!.source = decoded.source;

  // Assign monotonic sequence ID for sync protocol
  let globalState = getOrCreateGlobalState();
  entity!.sequenceId = globalState.nextSequenceId;
  globalState.nextSequenceId = globalState.nextSequenceId.plus(BigInt.fromI32(1));
  globalState.totalFacts = globalState.totalFacts.plus(BigInt.fromI32(isNew ? 1 : 0));
  globalState.lastUpdated = event.block.timestamp;
  globalState.save();

  entity!.save();
}
