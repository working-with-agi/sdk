import type { AuthState, Organization } from "./types.js";

/**
 * Auth client — receive a token, manage organizations (tenants).
 *
 *   const auth = new AuthClient();
 *   auth.setToken("eyJ...", {
 *     user: { id: "u1", name: "Alice" },
 *     organizations: [{ id: "org_1", name: "Acme" }],
 *   });
 *
 *   // Wire into API clients
 *   api.setAccessToken(auth.token!);
 *
 *   // Switch tenant
 *   auth.switchOrg("org_1", newToken);
 *   api.setAccessToken(auth.token!);
 */
export class AuthClient {
  private state: AuthState = { isAuthenticated: false };
  private orgs: Organization[] = [];
  private listeners: Array<(token: string) => void> = [];

  /** Current access token. */
  get token(): string | undefined {
    return this.state.accessToken;
  }

  /** Current auth state. */
  get authenticated(): boolean {
    return this.state.isAuthenticated;
  }

  /** Current organization (tenant). */
  get org(): Organization | undefined {
    return this.state.organization;
  }

  /** All organizations the user belongs to. */
  get organizations(): readonly Organization[] {
    return this.orgs;
  }

  /** Set token and user info after login. */
  setToken(
    accessToken: string,
    info: {
      user: { id: string; name?: string; email?: string };
      organizations?: Organization[];
    },
  ): void {
    this.state = {
      isAuthenticated: true,
      user: info.user,
      accessToken,
    };
    this.orgs = info.organizations ?? [];
    if (this.orgs.length === 1) {
      this.state.organization = this.orgs[0];
    }
  }

  /** Clear auth state. */
  clear(): void {
    this.state = { isAuthenticated: false };
    this.orgs = [];
  }

  /** Switch active organization. Pass the org-scoped token. */
  switchOrg(orgId: string, orgScopedToken: string): void {
    const found = this.orgs.find((o) => o.id === orgId);
    if (!found) throw new Error(`Org not found: ${orgId}`);
    this.state.organization = found;
    this.state.accessToken = orgScopedToken;
    this.notify(orgScopedToken);
  }

  /** Update token (e.g. after refresh). */
  refreshToken(token: string): void {
    this.state.accessToken = token;
    this.notify(token);
  }

  /** Subscribe to token changes. Returns unsubscribe fn. */
  onTokenChange(cb: (token: string) => void): () => void {
    this.listeners.push(cb);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== cb);
    };
  }

  private notify(token: string): void {
    for (const cb of this.listeners) cb(token);
  }
}
