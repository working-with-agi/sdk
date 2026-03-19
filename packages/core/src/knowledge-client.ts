import { HttpClient } from "./http-client.js";
import type {
  IngestResult,
  KnowledgeSearchResponse,
  KnowledgeContextResponse,
  SyncConnection,
  CreateSyncParams,
  SyncResult,
} from "./types.js";

/**
 * Knowledge base client — upload docs, search, sync external sources.
 *
 *   const kb = new KnowledgeClient("https://hub:8610", "key");
 *
 *   // Manual upload
 *   await kb.upload(pdfFile);
 *
 *   // Search & context
 *   const hits = await kb.search("how does auth work?");
 *   const ctx = await kb.context("deploy steps");
 *
 *   // Sync from external service
 *   await kb.connect({ provider: "sharepoint", name: "Team Docs", config: { site_url: "..." } });
 *   await kb.sync("conn-id");
 */
export class KnowledgeClient extends HttpClient {
  // --- Document management ---

  /** Upload a file (PDF, DOCX, PPTX, Markdown, text). */
  async upload(file: File | Blob, id?: string): Promise<IngestResult> {
    const form = new FormData();
    form.append("file", file);
    if (id) form.append("document_id", id);
    return this.fetch("/api/v1/knowledge/ingest", {
      method: "POST",
      body: form,
      headers: {},
    });
  }

  /** Search the knowledge base. */
  async search(query: string, limit = 10, documentId?: string): Promise<KnowledgeSearchResponse> {
    return this.fetch("/api/v1/knowledge/search", {
      method: "POST",
      body: JSON.stringify({ query, limit, document_id: documentId ?? "" }),
    });
  }

  /** Get RAG context for a query. */
  async context(query: string, limit = 5): Promise<KnowledgeContextResponse> {
    return this.fetch("/api/v1/knowledge/context", {
      method: "POST",
      body: JSON.stringify({ query, limit }),
    });
  }

  /** Remove a document. */
  async remove(documentId: string): Promise<void> {
    await this.fetch(`/api/v1/knowledge/${documentId}`, { method: "DELETE" });
  }

  // --- External sync ---

  /** List sync connections. */
  async connections(): Promise<SyncConnection[]> {
    return this.fetch("/api/v1/sync");
  }

  /** Create a new sync connection (Google Drive, SharePoint, Notion, etc.). */
  async connect(params: CreateSyncParams): Promise<SyncConnection> {
    return this.fetch("/api/v1/sync", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  /** Trigger sync for a connection. */
  async sync(connectionId: string): Promise<SyncResult> {
    return this.fetch(`/api/v1/sync/${connectionId}/run`, { method: "POST" });
  }

  /** Pause a sync connection. */
  async pause(connectionId: string): Promise<void> {
    await this.fetch(`/api/v1/sync/${connectionId}/pause`, { method: "POST" });
  }

  /** Resume a paused sync connection. */
  async resume(connectionId: string): Promise<void> {
    await this.fetch(`/api/v1/sync/${connectionId}/resume`, { method: "POST" });
  }

  /** Delete a sync connection and its synced documents. */
  async disconnect(connectionId: string): Promise<void> {
    await this.fetch(`/api/v1/sync/${connectionId}`, { method: "DELETE" });
  }
}
