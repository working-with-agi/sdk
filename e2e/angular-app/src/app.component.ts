import { Component, OnInit, ChangeDetectorRef, NgZone, inject } from "@angular/core";
import { NgIf, NgFor } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { AgiTerminalComponent } from "@working-with-agi/angular";
import { AgiApiClient } from "@working-with-agi/sdk";
import type { ToolInfo } from "@working-with-agi/sdk";

@Component({
  selector: "app-root",
  standalone: true,
  imports: [NgIf, NgFor, FormsModule, AgiTerminalComponent],
  template: `
    <!-- Launcher -->
    <div *ngIf="!sessionId" class="launcher">
      <div class="hero">
        <h1>WorkWithAGI</h1>
        <p>Angular Demo — AI Terminal</p>
      </div>
      <div *ngIf="availableTools.length > 0" class="prompt-row">
        <input
          class="prompt-input"
          placeholder="Initial prompt (optional)"
          [(ngModel)]="prompt"
          (keydown.enter)="availableTools.length > 0 && launchSession(availableTools[0].name)"
        />
      </div>
      <div *ngIf="availableTools.length > 0" class="tool-grid">
        <button
          *ngFor="let t of availableTools"
          class="tool-btn"
          [disabled]="launching"
          (click)="launchSession(t.name)"
        >
          {{ t.label }}
        </button>
      </div>
      <p *ngIf="availableTools.length === 0" class="hint-text">
        {{ error ? 'Server unavailable: ' + error : 'Connecting to server...' }}
      </p>
      <p *ngIf="error && availableTools.length > 0" class="error-text">{{ error }}</p>
    </div>

    <!-- Terminal session -->
    <div *ngIf="sessionId" class="app">
      <div class="toolbar">
        <span class="brand">WorkWithAGI</span>
        <span class="sep"></span>
        <span class="dot" [class.green]="connected" [class.yellow]="!connected"></span>
        <span class="tool-name">{{ selectedLabel }}</span>
        <span class="session-label">{{ sessionId.slice(0, 16) }}</span>
        <span class="sep"></span>
        <button class="tb" *ngFor="let role of roles" (click)="addAgent(role)">+ {{ role }}</button>
        <span class="sep"></span>
        <button class="tb" (click)="toggleTheme()">{{ theme === 'dark' ? '\u263E' : '\u2600' }}</button>
        <button class="tb end" (click)="endSession()">End</button>
      </div>
      <div class="terminal">
        <agi-terminal
          [endpoint]="endpoint"
          [apiKey]="apiKey"
          [sessionId]="sessionId"
          [theme]="theme"
          [fontSize]="14"
          (connected)="onConnect()"
          (disconnected)="onDisconnect()"
        ></agi-terminal>
      </div>
    </div>
  `,
  styles: [
    `
    :host { display: block; width: 100vw; height: 100vh; font-family: "Inter", system-ui, sans-serif; color: #c0caf5; }

    .launcher { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 24px; height: 100%; padding: 32px; }
    .hero { text-align: center; }
    .hero h1 { font-size: 28px; font-weight: 700; color: #7aa2f7; margin-bottom: 8px; }
    .hero p { font-size: 14px; color: #565f89; }
    .tool-grid { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
    .tool-btn { padding: 10px 20px; border-radius: 8px; border: none; background: #7aa2f7; color: #1a1b26; font-weight: 600; font-size: 14px; cursor: pointer; }
    .tool-btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
    .tool-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .error-text { color: #f7768e; font-size: 13px; }
    .hint-text { color: #565f89; font-size: 14px; }
    .prompt-row { width: 100%; max-width: 480px; }
    .prompt-input { width: 100%; padding: 10px 14px; border-radius: 8px; border: 1px solid #414868; background: #24283b; color: #c0caf5; font-size: 13px; outline: none; box-sizing: border-box; }
    .prompt-input:focus { border-color: #7aa2f7; }

    .app { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
    .toolbar { display: flex; align-items: center; gap: 6px; padding: 0 12px; height: 36px; background: rgba(22,22,30,0.85); border-bottom: 1px solid #414868; flex-shrink: 0; user-select: none; }
    .brand { font-size: 13px; font-weight: 700; color: #7aa2f7; }
    .sep { width: 1px; height: 18px; background: #414868; }
    .dot { width: 8px; height: 8px; border-radius: 50%; }
    .dot.green { background: #9ece6a; }
    .dot.yellow { background: #e0af68; }
    .tool-name { font-size: 13px; font-weight: 600; color: #7aa2f7; }
    .session-label { font-size: 11px; color: #565f89; font-family: "JetBrains Mono", "Fira Code", monospace; }
    .tb { padding: 3px 10px; border-radius: 4px; border: 1px solid #414868; background: transparent; color: #565f89; font-size: 11px; cursor: pointer; }
    .tb:hover { color: #c0caf5; border-color: #565f89; }
    .tb.end { margin-left: auto; }
    .tb.end:hover { background: #f7768e; color: #1a1b26; border-color: #f7768e; }
    .terminal { flex: 1; min-height: 0; overflow: hidden; }
    `,
  ],
})
export class AppComponent implements OnInit {
  readonly endpoint = window.location.origin;
  readonly apiKey = "test-key-123";
  readonly roles = ["developer", "reviewer", "tester"];

  private api = new AgiApiClient(this.endpoint, this.apiKey);
  private cdr = inject(ChangeDetectorRef);
  private zone = inject(NgZone);

  tools: Record<string, ToolInfo> = {};
  availableTools: { name: string; label: string }[] = [];
  sessionId = "";
  selectedLabel = "";
  theme: "dark" | "light" = "dark";
  connected = false;
  error = "";
  launching = false;
  prompt = "";

  ngOnInit() {
    this.zone.run(() => {
      this.api.listTools().then((tools) => {
        this.tools = tools;
        this.availableTools = Object.entries(this.tools)
          .filter(([, info]) => info.available)
          .map(([name, info]) => ({ name, label: info.label }));
        this.cdr.detectChanges();
      }).catch((e: any) => {
        this.error = e.message;
        this.cdr.detectChanges();
      });
    });
  }

  launchSession(tool: string) {
    if (this.launching) return;
    this.launching = true;
    this.error = "";
    this.api.createSession({
      user_id: "demo-user",
      tool,
      sandbox: true,
      label: this.tools[tool]?.label ?? tool,
      prompt: this.prompt || undefined,
    }).then((session) => {
      this.sessionId = session.session_id;
      this.selectedLabel = this.tools[tool]?.label ?? tool;
      this.cdr.detectChanges();
    }).catch((e: any) => {
      this.error = e.message;
      this.cdr.detectChanges();
    }).finally(() => {
      this.launching = false;
      this.cdr.detectChanges();
    });
  }

  endSession() {
    if (this.sessionId) {
      this.api.destroySession(this.sessionId).catch(() => {});
    }
    this.sessionId = "";
    this.connected = false;
    this.selectedLabel = "";
    this.cdr.detectChanges();
  }

  addAgent(role: string) {
    if (!this.sessionId) return;
    this.api.addPane(this.sessionId, { tool: "bash", role }).catch((e: any) => {
      this.error = e.message;
      this.cdr.detectChanges();
    });
  }

  toggleTheme() {
    this.theme = this.theme === "dark" ? "light" : "dark";
  }

  onConnect() {
    this.connected = true;
  }

  onDisconnect() {
    this.connected = false;
  }
}
