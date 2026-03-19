import { HttpClient } from "./http-client.js";
import type {
  IngestResult,
  KnowledgeSearchResponse,
  KnowledgeContextResponse,
} from "./types.js";

/**
 * REST API client for KnowledgeHub (document RAG service).
 *
 * KnowledgeHub runs as a separate service (default port 8610)
 * from the agiterm terminal server.
 */
export class KnowledgeClient extends HttpClient {
  /**
   * Upload and ingest a document for RAG.
   * Supports PDF, DOCX, PPTX, Markdown, and plain text.
   */
  async ingest(file: File | Blob, documentId?: string): Promise<IngestResult> {
    const form = new FormData();
    form.append("file", file);
    if (documentId) {
      form.append("document_id", documentId);
    }

    return this.fetch("/api/v1/knowledge/ingest", {
      method: "POST",
      body: form,
      // Don't set Content-Type — browser will set multipart boundary
      headers: {},
    });
  }

  /** Semantic search across the tenant's knowledge base. */
  async search(
    query: string,
    options: { limit?: number; documentId?: string } = {},
  ): Promise<KnowledgeSearchResponse> {
    return this.fetch("/api/v1/knowledge/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        limit: options.limit ?? 10,
        document_id: options.documentId ?? "",
      }),
    });
  }

  /** Build RAG context string from knowledge base. */
  async buildContext(
    query: string,
    limit: number = 5,
  ): Promise<KnowledgeContextResponse> {
    return this.fetch("/api/v1/knowledge/context", {
      method: "POST",
      body: JSON.stringify({ query, limit }),
    });
  }

  /** Delete a document from the knowledge base. */
  async deleteDocument(documentId: string): Promise<void> {
    await this.fetch(`/api/v1/knowledge/${documentId}`, {
      method: "DELETE",
    });
  }
}
