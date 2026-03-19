/**
 * Base HTTP client with API key authentication.
 */
export class HttpClient {
  protected endpoint: string;
  protected apiKey: string;

  constructor(endpoint: string, apiKey: string = "") {
    this.endpoint = endpoint.replace(/\/$/, "");
    this.apiKey = apiKey;
  }

  async fetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const isFormData = options.body instanceof FormData;
    const headers: Record<string, string> = {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...((options.headers as Record<string, string>) ?? {}),
    };

    if (this.apiKey) {
      headers["X-API-Key"] = this.apiKey;
    }

    const res = await fetch(`${this.endpoint}${path}`, {
      ...options,
      headers,
    });

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`WorkAGI API error ${res.status}: ${body}`);
    }

    return res.json();
  }
}
