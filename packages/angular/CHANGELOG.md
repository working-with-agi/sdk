# @working-with-agi/angular

## 0.4.0

### Minor Changes

- [#4](https://github.com/working-with-agi/sdk/pull/4) [`73f6690`](https://github.com/working-with-agi/sdk/commit/73f6690b663565d23ffd035c22a5f4628ff541e7) Thanks [@kaz-tk](https://github.com/kaz-tk)! - Connect terminals with a Logto access token, and register MCP servers per session.

  - `accessToken` on `AgiTerminal` / `AgiRenderedTerminal` (core, Vue, React, Angular), `WorkWithAI` and `AgiPilot`. It is sent to agiterm-server as `?token=` and takes precedence over `apiKey`. New helper: `wsAuthQuery()`.
  - `CreateSessionParams.mcp_servers` (`McpServerConfig`): remote MCP servers that Claude Code in the session should use. `user_id` is now optional (with an access token the server uses the token's subject).
  - `@work-with-ai/vue` now depends on `@xterm/xterm` and its addons, which it imports directly. This fixes the package build.

### Patch Changes

- Updated dependencies [[`73f6690`](https://github.com/working-with-agi/sdk/commit/73f6690b663565d23ffd035c22a5f4628ff541e7)]:
  - @work-with-ai/sdk@0.4.0

## 0.3.0

### Minor Changes

- Rewrite terminal to use AgentServer native WebSocket protocol

  - Connect via native WebSocket to `/ws/tmux/{session_id}` (not Socket.IO)
  - Binary frame protocol for PTY I/O: `[pane_id_len][pane_id][data]`
  - JSON control messages for session/window/pane management
  - Full tmux multiplexer support: split, resize, focus, layouts
  - Remove socket.io-client dependency
  - Expose TmuxSession/TmuxWindow/TmuxPane types

### Patch Changes

- Updated dependencies []:
  - @working-with-agi/sdk@0.3.0

## 0.2.0

### Minor Changes

- Initial release of WorkWithAGI SDK

  - `@working-with-agi/sdk` — Core SDK: AgiTerminal, AgiCodeSearch, WorkAGI facade
  - `@working-with-agi/react` — React components + hooks
  - `@working-with-agi/vue` — Vue 3 components + composables
  - `@working-with-agi/angular` — Angular components + services

### Patch Changes

- Updated dependencies []:
  - @working-with-agi/sdk@0.2.0
