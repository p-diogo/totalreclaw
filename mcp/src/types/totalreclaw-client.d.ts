/**
 * Ambient type declarations for @totalreclaw/client.
 *
 * The client package ships TypeScript source but its dist/ may not be built
 * in every environment.  These declarations cover the subset of the API that
 * the MCP server actually imports.
 */
declare module '@totalreclaw/client' {
  export interface FactMetadata {
    source?: string;
    timestamp?: Date;
    importance?: number;
    accessCount?: number;
    lastAccessed?: Date;
    tags?: string[];
  }

  export interface Fact {
    id: string;
    text: string;
    embedding: number[];
    metadata: FactMetadata;
    decayScore: number;
    createdAt: Date;
  }

  export interface RerankedResult {
    fact: Fact;
    score: number;
    vectorScore: number;
    textScore: number;
    decayAdjustedScore: number;
  }

  export interface TotalReclawConfig {
    serverUrl: string;
    modelPath?: string;
    lshConfig?: Record<string, unknown>;
    timeout?: number;
  }

  export class TotalReclaw {
    constructor(config: TotalReclawConfig);
    init(): Promise<void>;
    register(masterPassword: string): Promise<string>;
    login(userId: string, masterPassword: string, salt: Buffer): Promise<void>;
    remember(text: string, metadata?: FactMetadata): Promise<string>;
    recall(query: string, k?: number): Promise<RerankedResult[]>;
    forget(factId: string): Promise<void>;
    getUserId(): string | null;
    getSalt(): Buffer | null;
    isReady(): boolean;
  }
}
