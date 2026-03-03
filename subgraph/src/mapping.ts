/**
 * Subgraph mapping for EventfulDataEdge.
 *
 * Handles Log(bytes) events emitted by the EventfulDataEdge contract.
 * Each event contains an encrypted Protobuf-serialized TotalReclawFact.
 * The mapping extracts metadata fields and stores them as Fact records
 * with inverted BlindIndex entities for efficient hash_in queries.
 *
 * IMPORTANT: The subgraph stores encrypted data. It never sees plaintext.
 * The blind_indices are SHA-256 hashes — the subgraph can match them but
 * cannot reverse them to learn the original content.
 */

import { Bytes, BigDecimal, BigInt, log } from "@graphprotocol/graph-ts";
import { Log } from "../generated/EventfulDataEdge/EventfulDataEdge";
import { Fact, BlindIndex, GlobalState } from "../generated/schema";
import { decodeFact, DecodedFact } from "./protobuf";

const GLOBAL_STATE_ID = "global";
const INACTIVE_THRESHOLD = BigDecimal.fromString("0.3");

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
  let data = event.params.data;
  if (data.length == 0) {
    log.warning("Empty Log event in tx {}", [event.transaction.hash.toHexString()]);
    return;
  }

  let decoded = decodeFact(data);

  // Use Protobuf ID or fall back to tx hash + log index
  let factId = decoded.id;
  if (factId == "") {
    factId = event.transaction.hash.toHexString() + "-" + event.logIndex.toString();
  }

  let fact = Fact.load(factId);
  let isNew = fact == null;
  if (fact == null) {
    fact = new Fact(factId);
  }

  // Owner: from Protobuf or tx.from
  let owner: Bytes;
  if (decoded.owner != "") {
    owner = Bytes.fromHexString(decoded.owner);
  } else {
    owner = event.transaction.from;
  }
  fact!.owner = owner;

  fact!.encryptedBlob = decoded.encryptedBlob;
  fact!.encryptedEmbedding = decoded.encryptedEmbedding;
  fact!.decayScore = decoded.decayScore;
  fact!.isActive = decoded.decayScore.ge(INACTIVE_THRESHOLD);
  fact!.contentFp = decoded.contentFp;
  fact!.agentId = decoded.agentId;
  fact!.version = decoded.version;
  fact!.source = decoded.source;
  fact!.blockNumber = event.block.number;
  fact!.timestamp = event.block.timestamp;
  fact!.txHash = event.transaction.hash;

  // Assign monotonic sequence ID
  let state = getOrCreateGlobalState();
  fact!.sequenceId = state.nextSequenceId;
  state.nextSequenceId = state.nextSequenceId.plus(BigInt.fromI32(1));
  if (isNew) {
    state.totalFacts = state.totalFacts.plus(BigInt.fromI32(1));
  }
  state.lastUpdated = event.block.timestamp;
  state.save();

  fact!.save();

  // Create inverted BlindIndex entities
  let indices = decoded.blindIndices;
  for (let i = 0; i < indices.length; i++) {
    let hash = indices[i];
    let indexId = factId + "-" + hash;
    let blindIndex = new BlindIndex(indexId);
    blindIndex.hash = hash;
    blindIndex.fact = factId;
    blindIndex.owner = owner;
    blindIndex.save();
  }

  log.info("Indexed fact {} with {} blind indices for owner {}", [
    factId,
    indices.length.toString(),
    owner.toHexString()
  ]);
}
