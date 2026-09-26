/**
 * Put the planning inputs into the WorkWithAI knowledge base so that agents (and people)
 * can search them, and set up a recurring sync of the shop-quote folder.
 *
 *   npm run ingest                                 # fleet/shop JSON + REQUIREMENTS/README
 *   npm run ingest -- --pdf-dir ./manuals          # + PDFs (engine manuals, WSPG, contracts, quotes)
 *   npm run ingest -- --drive-folder <FOLDER_ID>   # + monthly Google Drive sync of shop quotes
 *   npm run ingest -- --drive-folder <ID> --sync-now
 *   npm run ingest -- --dry-run                    # show what would happen, no network calls
 *   npm run ingest -- --force                      # re-upload even if unchanged
 *
 * Idempotency
 *   - every file gets a stable document id derived from its path (engine-mro--data--fleet_visits-json),
 *     so re-running replaces the same document instead of adding a copy;
 *   - a local manifest (.ingest-manifest.json, git-ignored) stores each file's SHA-256; unchanged
 *     files are skipped, changed files are removed and uploaded again under the same id;
 *   - the sync connection is looked up by name first and only created once.
 */
import { createHash } from "node:crypto";
import { readFile, readdir, writeFile } from "node:fs/promises";
import { basename, extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { KnowledgeClient } from "@work-with-ai/sdk";
import type { CreateSyncParams, SyncConnection } from "@work-with-ai/sdk";

import { loadConfig, redact } from "./config.js";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const EXAMPLE_ROOT = resolve(HERE, "..");
const ANALYSIS_DIR = resolve(EXAMPLE_ROOT, "../engine-shop-selection-mc");
const MANIFEST = join(EXAMPLE_ROOT, ".ingest-manifest.json");

/** The inputs the Python analysis reads, plus the documents the reviewer checks against. */
const DEFAULT_FILES = [
  "data/fleet_visits.json",
  "data/fleet_visits_lifecycle.json",
  "data/shop_quotes.json",
  "REQUIREMENTS.md",
  "README.md",
];

const MIME: Record<string, string> = {
  ".json": "application/json",
  ".md": "text/markdown",
  ".pdf": "application/pdf",
  ".txt": "text/plain",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};

const SYNC_NAME = "engine-mro shop quotes";
/** 1st of every month, 03:00 (server time) — just before the monthly re-plan. */
const MONTHLY = "0 3 1 * *";

type Manifest = Record<string, { sha256: string; uploadedAt: string; chunks: number }>;

/** Stable, URL-safe document id (it ends up in DELETE /api/v1/knowledge/{id}). */
export function docId(relPath: string): string {
  return `engine-mro--${relPath.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase()}`;
}

async function loadManifest(): Promise<Manifest> {
  try {
    return JSON.parse(await readFile(MANIFEST, "utf8")) as Manifest;
  } catch {
    return {};
  }
}

async function listPdfs(dir: string): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true });
  return entries
    .filter((e) => e.isFile() && extname(e.name).toLowerCase() === ".pdf")
    .map((e) => join(dir, e.name))
    .sort();
}

async function main(): Promise<void> {
  const { values } = parseArgs({
    options: {
      "pdf-dir": { type: "string" },
      "drive-folder": { type: "string" },
      "sync-now": { type: "boolean", default: false },
      "dry-run": { type: "boolean", default: false },
      force: { type: "boolean", default: false },
    },
  });
  const dryRun = values["dry-run"] ?? false;

  // (absolute path, id key) pairs
  const files: Array<{ abs: string; key: string }> = DEFAULT_FILES.map((rel) => ({
    abs: join(ANALYSIS_DIR, rel),
    key: rel,
  }));
  if (values["pdf-dir"]) {
    const dir = resolve(values["pdf-dir"]);
    for (const abs of await listPdfs(dir)) files.push({ abs, key: `pdf/${relative(dir, abs)}` });
  }

  const cfg = dryRun ? null : loadConfig();
  const kb = cfg ? new KnowledgeClient(cfg.knowledgeEndpoint, cfg.apiKey) : null;
  if (cfg && kb) {
    if (cfg.accessToken) kb.setAccessToken(cfg.accessToken);
    console.log(`knowledge endpoint: ${cfg.knowledgeEndpoint}  api key: ${redact(cfg.apiKey)}`);
  }

  const manifest = await loadManifest();
  for (const { abs, key } of files) {
    const bytes = await readFile(abs);
    const sha256 = createHash("sha256").update(bytes).digest("hex");
    const id = docId(key);
    if (!values.force && manifest[id]?.sha256 === sha256) {
      console.log(`skip    ${key}  (unchanged, id=${id})`);
      continue;
    }
    if (dryRun || !kb) {
      console.log(`upload  ${key}  -> id=${id}  (${bytes.length} bytes, dry run)`);
      continue;
    }
    if (manifest[id]) {
      // Replace, not duplicate: drop the old chunks first. A 404 here just means it is already gone.
      await kb.remove(id).catch((e: unknown) => console.warn(`  remove ${id}: ${String(e)}`));
    }
    const type = MIME[extname(abs).toLowerCase()] ?? "application/octet-stream";
    // Node 20+ has global File/Blob; File carries the filename into the multipart body.
    const file = new File([bytes], basename(abs), { type });
    const res = await kb.upload(file, id);
    manifest[id] = { sha256, uploadedAt: new Date().toISOString(), chunks: res.chunk_count };
    console.log(`upload  ${key}  -> id=${res.document_id}  chunks=${res.chunk_count}`);
  }
  if (!dryRun) await writeFile(MANIFEST, JSON.stringify(manifest, null, 2) + "\n");

  // --- recurring sync of the shop-quote folder -------------------------------------------
  const folder = values["drive-folder"];
  if (!folder) return;
  const params: CreateSyncParams = {
    provider: "google-drive",
    name: SYNC_NAME,
    config: { folder_id: folder },
    schedule: MONTHLY,
  };
  if (dryRun || !kb) {
    console.log(`connect ${JSON.stringify(params)} (dry run)`);
    return;
  }
  const existing: SyncConnection | undefined = (await kb.connections()).find((c) => c.name === SYNC_NAME);
  let conn: SyncConnection;
  if (existing) {
    conn = existing;
    if (existing.status === "paused") await kb.resume(existing.id);
    console.log(`sync    already connected: ${existing.id} (${existing.status}, ${existing.doc_count} docs, last ${existing.last_sync ?? "-"})`);
  } else {
    conn = await kb.connect(params);
    console.log(`sync    created ${conn.id}: ${conn.provider} folder=${folder} schedule="${MONTHLY}"`);
  }
  if (values["sync-now"]) {
    const r = await kb.sync(conn.id);
    console.log(`sync    run: +${r.added} ~${r.updated} -${r.removed}`);
  }
  // To stop temporarily: kb.pause(conn.id); to delete the connection and its docs: kb.disconnect(conn.id)
}

main().catch((e: unknown) => {
  console.error(e instanceof Error ? e.message : e);
  process.exitCode = 1;
});
