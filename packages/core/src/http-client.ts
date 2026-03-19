/**
 * Base HTTP client with API key or Bearer token authentication.
 *
 * Supports two auth modes:
 * - **API Key**: static key sent via `X-API-Key` header (legacy/service usage)
 * - **Access Token**: Logto JWT sent via `Authorization: Bearer` header (user auth)
 *
 * If both are set, Bearer token takes precedence.
 */
export class HttpClient {
  protected endpoint: string;
  protected apiKey: string;
  protected accessToken: string;

  constructor(endpoint: string, apiKey: string = "") {
    this.endpoint = endpoint.replace(/\/$/, "");
    this.apiKey = apiKey;
    this.accessToken = "";
  }

  /**
   * Set the API key for `X-API-Key` header authentication.
   * Clears any previously set access token.
   */
  setApiKey(key: string): void {
    this.apiKey = key;
    this.accessToken = "";
  }

  /**
   * Set a Logto JWT access token for `Authorization: Bearer` authentication.
   * When set, Bearer token takes precedence over API key.
   */
  setAccessToken(token: string): void {
    this.accessToken = token;
  }

  async fetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const isFormData = options.body instanceof FormData;
    const headers: Record<string, string> = {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...((options.headers as Record<string, string>) ?? {}),
    };

    if (this.accessToken) {
      headers["Authorization"] = `Bearer ${this.accessToken}`;
    } else if (this.apiKey) {
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
