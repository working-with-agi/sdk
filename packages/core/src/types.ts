// --- Theme Types ---

export interface TerminalTheme {
  background?: string;
  foreground?: string;
  cursor?: string;
  selectionBackground?: string;
  black?: string;
  red?: string;
  green?: string;
  yellow?: string;
  blue?: string;
  magenta?: string;
  cyan?: string;
  white?: string;
  brightBlack?: string;
  brightRed?: string;
  brightGreen?: string;
  brightYellow?: string;
  brightBlue?: string;
  brightMagenta?: string;
  brightCyan?: string;
  brightWhite?: string;
}

// --- Terminal Types ---

export interface TerminalOptions {
  /** agiterm-server base URL (e.g. "https://your-server:8600") */
  endpoint: string;
  /** API key for authentication */
  apiKey?: string;
  /** Session ID to reconnect to (obtained from REST API) */
  sessionId?: string;
  /** Built-in theme preset ("dark" | "light") or custom theme object */
  theme?: "dark" | "light" | TerminalTheme;
  /** Font size in pixels */
  fontSize?: number;
  /** Font family */
  fontFamily?: string;
  /** Cursor style */
  cursorStyle?: "block" | "underline" | "bar";
  /** Enable WebGL renderer (better performance) */
  webgl?: boolean;
  /** Callback when PTY output is received */
  onOutput?: (data: Uint8Array) => void;
  /** Callback when connection opens */
  onConnect?: () => void;
  /** Callback when connection closes */
  onDisconnect?: () => void;
  /** Callback when connection error occurs */
  onError?: (error: Event) => void;
}

export interface TerminalInstance {
  sendInput(data: string): void;
  sendInputBytes(data: Uint8Array): void;
  resize(cols: number, rows: number): void;
  sendControl(message: Record<string, unknown>): void;
  dispose(): void;
}

export interface RenderedTerminalOptions extends TerminalOptions {
  /** DOM element or CSS selector to mount the terminal into */
  container: string | HTMLElement;
}

// --- REST API Types ---

export interface CreateSessionParams {
  user_id: string;
  tool?: string;
  sandbox?: boolean;
  shell?: string;
  cols?: number;
  rows?: number;
  label?: string;
  /** Initial prompt/command to send after connection */
  prompt?: string;
}

export interface SessionInfo {
  session_id: string;
  tenant_id: string;
  user_id: string;
  tool: string;
  label: string;
  ws_url: string;
}

export interface ToolInfo {
  label: string;
  available: boolean;
  binary: string;
}

// --- Pane Management Types ---

export interface AddPaneParams {
  tool?: string;
  role?: string;
  cols?: number;
  rows?: number;
}

export interface PaneInfo {
  pane_id: string;
  tool: string;
  role: string;
  title: string;
}

export interface LayoutTree {
  session_id: string;
  layout: Record<string, unknown>;
}

// --- Knowledge (RAG) Types ---

export interface IngestResult {
  document_id: string;
  filename: string;
  chunk_count: number;
}

export interface KnowledgeSearchResult {
  score: number;
  chunk: string;
  document_id: string;
  filename: string;
  chunk_index: number;
}

export interface KnowledgeSearchResponse {
  query: string;
  results: KnowledgeSearchResult[];
}

export interface KnowledgeContextResponse {
  query: string;
  context: string;
}
