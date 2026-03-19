# @working-with-agi/angular

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
