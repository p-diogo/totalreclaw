/**
 * TotalReclaw API Module
 *
 * HTTP client and Protobuf serialization for server communication.
 */

export { TotalReclawClient } from './client';
export { ProtobufSerializer, protobufSerializer } from './protobuf';

// Sync (v0.3.1b)
export {
  SyncClient,
  SyncState,
  reconcileLocalFacts,
} from './sync';

export type {
  SyncedFact,
  LocalPendingFact,
  SyncResult,
  ReconciliationResult,
  SyncClientConfig,
} from './sync';
