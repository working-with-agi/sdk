import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Connection settings for the Node scripts (ingest.ts / run-monthly.ts).
 *
 * Everything comes from the environment; nothing is hardcoded.
 *   WORKWITHAI_ENDPOINT            agiterm-server base URL, e.g. https://agi.example.com:8600
 *   WORKWITHAI_API_KEY             API key (sent as X-API-Key by the SDK)
 *   WORKWITHAI_USER                user_id the planning sessions run as
 *   WORKWITHAI_KNOWLEDGE_ENDPOINT  optional: knowledge hub URL if it is served separately
 *                                  (the SDK docs show a separate hub on :8610); defaults to WORKWITHAI_ENDPOINT
 *   WORKWITHAI_ACCESS_TOKEN        optional: Logto JWT; if set it takes precedence over the API key
 */
export interface ExampleConfig {
  endpoint: string;
  knowledgeEndpoint: string;
  apiKey: string;
  accessToken?: string;
  userId: string;
}

function required(env: NodeJS.ProcessEnv, name: string): string {
  const v = env[name]?.trim();
  if (!v) {
    throw new Error(`環境変数 ${name} が未設定です（README の「実行方法」を参照）`);
  }
  return v;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): ExampleConfig {
  const endpoint = required(env, "WORKWITHAI_ENDPOINT").replace(/\/$/, "");
  const accessToken = env.WORKWITHAI_ACCESS_TOKEN?.trim() || undefined;
  // An API key is required unless a bearer token is supplied instead.
  const apiKey = accessToken ? (env.WORKWITHAI_API_KEY?.trim() ?? "") : required(env, "WORKWITHAI_API_KEY");
  return {
    endpoint,
    knowledgeEndpoint: (env.WORKWITHAI_KNOWLEDGE_ENDPOINT?.trim() || endpoint).replace(/\/$/, ""),
    apiKey,
    accessToken,
    userId: required(env, "WORKWITHAI_USER"),
  };
}

/** Never print a secret; show only enough to tell keys apart. */
export function redact(secret: string): string {
  if (!secret) return "(none)";
  return secret.length <= 8 ? "****" : `${secret.slice(0, 4)}…${secret.slice(-2)}`;
}

/** This example's folder, whether running from src/ (tsc) or dist/node/ (bundled). */
export function exampleRoot(moduleUrl: string): string {
  let dir = dirname(fileURLToPath(moduleUrl));
  while (!existsSync(join(dir, "package.json"))) {
    const up = dirname(dir);
    if (up === dir) throw new Error("package.json not found above " + moduleUrl);
    dir = up;
  }
  return dir;
}
