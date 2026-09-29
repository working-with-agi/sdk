---
"@work-with-ai/sdk": minor
"@work-with-ai/vue": minor
"@work-with-ai/react": minor
"@work-with-ai/angular": minor
---

Connect terminals with a Logto access token, and register MCP servers per session.

- `accessToken` on `AgiTerminal` / `AgiRenderedTerminal` (core, Vue, React, Angular), `WorkWithAI` and `AgiPilot`. It is sent to agiterm-server as `?token=` and takes precedence over `apiKey`. New helper: `wsAuthQuery()`.
- `CreateSessionParams.mcp_servers` (`McpServerConfig`): remote MCP servers that Claude Code in the session should use. `user_id` is now optional (with an access token the server uses the token's subject).
- `@work-with-ai/vue` now depends on `@xterm/xterm` and its addons, which it imports directly. This fixes the package build.
