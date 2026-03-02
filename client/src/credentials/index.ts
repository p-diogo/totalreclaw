/**
 * TotalReclaw Credentials Module
 *
 * Provides secure credential storage (OS keychain) and session management
 * (in-memory key caching with automatic expiry).
 */

export {
  storeCredentials,
  getCredentials,
  deleteCredentials,
  hasCredentials,
  isKeychainAvailable,
} from './keychain';

export {
  SessionManager,
} from './session';

export type {
  DerivedKeys,
  SessionManagerConfig,
} from './session';
