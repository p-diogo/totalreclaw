/**
 * Minimal Protobuf decoder for OpenMemoryFact messages in AssemblyScript.
 *
 * The subgraph runs AssemblyScript (NOT TypeScript). We cannot use protobufjs.
 * Instead, we implement a minimal wire-format decoder for the fields we need.
 *
 * Protobuf wire format reference:
 *   - Field key = (field_number << 3) | wire_type
 *   - Wire type 0 = varint (int32, bool, enum)
 *   - Wire type 1 = 64-bit (double)
 *   - Wire type 2 = length-delimited (string, bytes, embedded messages, repeated)
 *
 * OpenMemoryFact fields (from openmemory.proto):
 *   1: string id                    (wire type 2)
 *   2: string timestamp             (wire type 2)
 *   3: string owner                 (wire type 2)
 *   4: bytes encrypted_blob         (wire type 2)
 *   5: repeated string blind_indices (wire type 2)
 *   6: double decay_score           (wire type 1)
 *   7: bool is_active               (wire type 0)
 *   8: int32 version                (wire type 0)
 *   9: string source                (wire type 2)
 */

import { Bytes, BigDecimal, BigInt } from "@graphprotocol/graph-ts";

export class DecodedFact {
  id: string;
  owner: string;
  encryptedBlob: Bytes;
  blindIndices: string[];
  decayScore: BigDecimal;
  isActive: boolean;
  version: i32;
  source: string;
  contentFp: string;
  agentId: string;

  constructor() {
    this.id = "";
    this.owner = "";
    this.encryptedBlob = Bytes.empty();
    this.blindIndices = [];
    this.decayScore = BigDecimal.zero();
    this.isActive = true;
    this.version = 0;
    this.source = "";
    this.contentFp = "";
    this.agentId = "";
  }
}

/**
 * Decode a varint from the byte array starting at offset.
 * Returns [value, newOffset].
 */
function decodeVarint(data: Bytes, offset: i32): i64[] {
  let result: i64 = 0;
  let shift: i32 = 0;
  let pos = offset;

  while (pos < data.length) {
    let byte = data[pos] as i64;
    result |= (byte & 0x7f) << shift;
    pos++;
    if ((byte & 0x80) == 0) break;
    shift += 7;
  }

  return [result, pos as i64];
}

/**
 * Decode an OpenMemoryFact from raw Protobuf bytes.
 *
 * This is a best-effort decoder. If the payload is malformed or contains
 * fields we do not recognize, we skip them gracefully.
 */
export function decodeFact(data: Bytes): DecodedFact {
  let fact = new DecodedFact();

  let offset: i32 = 0;

  while (offset < data.length) {
    // Read field key
    let keyResult = decodeVarint(data, offset);
    let key = keyResult[0] as i32;
    offset = keyResult[1] as i32;

    let fieldNumber = key >> 3;
    let wireType = key & 0x07;

    if (wireType == 0) {
      // Varint
      let valResult = decodeVarint(data, offset);
      let value = valResult[0];
      offset = valResult[1] as i32;

      if (fieldNumber == 7) {
        fact.isActive = value != 0;
      } else if (fieldNumber == 8) {
        fact.version = value as i32;
      }
    } else if (wireType == 1) {
      // 64-bit (double)
      if (offset + 8 > data.length) break;

      if (fieldNumber == 6) {
        // decay_score — read as raw bytes, convert to string for BigDecimal
        // AssemblyScript does not have native f64 from bytes, so we store raw
        // For PoC, we default to 1.0 and let the client set the real value
        fact.decayScore = BigDecimal.fromString("1.0");
      }
      offset += 8;
    } else if (wireType == 2) {
      // Length-delimited
      let lenResult = decodeVarint(data, offset);
      let len = lenResult[0] as i32;
      offset = lenResult[1] as i32;

      if (offset + len > data.length) break;

      let slice = data.subarray(offset, offset + len);

      if (fieldNumber == 1) {
        fact.id = slice.toString();
      } else if (fieldNumber == 3) {
        fact.owner = slice.toString();
      } else if (fieldNumber == 4) {
        fact.encryptedBlob = Bytes.fromUint8Array(slice);
      } else if (fieldNumber == 5) {
        let indices = fact.blindIndices;
        indices.push(slice.toString());
        fact.blindIndices = indices;
      } else if (fieldNumber == 9) {
        fact.source = slice.toString();
      }
      // Future fields (content_fp, agent_id) go here

      offset += len;
    } else if (wireType == 5) {
      // 32-bit fixed
      offset += 4;
    } else {
      // Unknown wire type — cannot skip safely, bail out
      break;
    }
  }

  return fact;
}
