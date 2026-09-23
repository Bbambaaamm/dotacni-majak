export interface D1PreparedStatementLike {
  bind(...values: unknown[]): D1PreparedStatementLike;
  first<T = unknown>(): Promise<T | null>;
}

export interface D1DatabaseLike {
  prepare(query: string): D1PreparedStatementLike;
}

export interface R2BucketLike {
  head(key: string): Promise<unknown | null>;
}

export interface VectorizeIndexLike {
  describe(): Promise<unknown>;
}

export interface Env {
  DB: D1DatabaseLike;
  RAW: R2BucketLike;
  SEARCH: VectorizeIndexLike;
  ENVIRONMENT: "local" | "staging" | "production";
  RELEASE_SHA?: string;
}
