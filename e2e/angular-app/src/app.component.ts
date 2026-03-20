import { Component, OnInit, ChangeDetectorRef, NgZone, inject } from "@angular/core";
import { NgIf, NgFor } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { AgiTerminalComponent } from "@working-with-agi/angular";
import { AgiApiClient, THEME_PRESETS } from "@working-with-agi/sdk";
import type { ToolInfo, TerminalTheme } from "@working-with-agi/sdk";

@Component({
  selector: "app-root",
  standalone: true,
  imports: [NgIf, NgFor, FormsModule, AgiTerminalComponent],
  template: `
    <div class="shell">
      <!-- Header -->
      <header class="header">
        <div class="header-left">
          <span class="logo">Work With AI</span>
          <span class="badge">Angular</span>
        </div>
        <div class="header-right">
          <select *ngIf="availableTools.length > 0" class="agent-select" [(ngModel)]="selectedTool" (ngModelChange)="onAgentChange()">
            <option *ngFor="let t of availableTools" [value]="t.name">{{ t.label }}</option>
          </select>
          <select class="theme-select" [(ngModel)]="themeName" (ngModelChange)="onThemeChange()">
            <optgroup label="Dark">
              <option *ngFor="let t of darkThemes" [value]="t.name">{{ t.label }}</option>
            </optgroup>
            <optgroup label="Light">
              <option *ngFor="let t of lightThemes" [value]="t.name">{{ t.label }}</option>
            </optgroup>
          </select>
          <button *ngIf="sessionId" class="btn-end" (click)="endSession()">End Session</button>
        </div>
      </header>

      <!-- Content -->
      <main class="content">
        <!-- Welcome -->
        <div *ngIf="!sessionId" class="welcome">
          <h1>AI Terminal</h1>
          <p>What would you like to work on?</p>

          <div class="input-bar">
            <input
              class="chat-input"
              placeholder="Describe your task..."
              [disabled]="launching || availableTools.length === 0"
              [(ngModel)]="prompt"
              (keydown.enter)="submit()"
            />
            <button
              class="send-btn"
              [disabled]="launching || availableTools.length === 0"
              (click)="submit()"
            >
              {{ launching ? '...' : 'Start' }}
            </button>
          </div>
          <p *ngIf="error" class="error-text">{{ error }}</p>
          <p *ngIf="availableTools.length === 0 && !error" class="hint">Connecting to server...</p>
        </div>

        <!-- Terminal session -->
        <div *ngIf="sessionId" class="terminal-wrap">
          <div class="terminal-bar">
            <span class="dot" [class.green]="connected" [class.yellow]="!connected"></span>
            <span class="bar-label">{{ selectedLabel }}</span>
            <span class="bar-session">{{ sessionId.slice(0, 12) }}</span>
          </div>
          <div class="terminal-body">
            <agi-terminal
              [endpoint]="endpoint"
              [apiKey]="apiKey"
              [sessionId]="sessionId"
              [theme]="currentTheme"
              [fontSize]="14"
              (connected)="onConnect()"
              (disconnected)="onDisconnect()"
            ></agi-terminal>
          </div>
        </div>
      </main>
    </div>
  `,
  styles: [
    `
    :host { display: block; width: 100vw; height: 100vh; }

    .shell {
      width: 100%; height: 100%;
      display: flex; flex-direction: column;
      font-family: "Inter", system-ui, sans-serif;
      color: #24292e;
      background: #f8f9fa;
    }

    .header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 20px; height: 48px;
      background: #ffffff;
      border-bottom: 1px solid #e1e4e8;
      flex-shrink: 0;
    }
    .header-left { display: flex; align-items: center; gap: 10px; }
    .header-right { display: flex; align-items: center; gap: 10px; }
    .logo { font-size: 16px; font-weight: 700; letter-spacing: -0.02em; color: #24292e; }
    .badge {
      font-size: 10px; font-weight: 600; text-transform: uppercase;
      padding: 2px 6px; border-radius: 4px;
      background: #eef2ff; color: #4f46e5;
    }

    .theme-select, .agent-select {
      padding: 5px 10px; border-radius: 6px;
      border: 1px solid #d1d5db;
      background: #ffffff; color: #374151;
      font-size: 12px; cursor: pointer; outline: none;
    }
    .theme-select:focus, .agent-select:focus { border-color: #4f46e5; }

    .btn-end {
      padding: 5px 12px; border-radius: 6px;
      border: 1px solid #fecaca;
      background: transparent; color: #dc2626;
      font-size: 12px; cursor: pointer; transition: all 0.15s;
    }
    .btn-end:hover { background: #dc2626; color: #ffffff; }

    .content { flex: 1; min-height: 0; display: flex; flex-direction: column; }

    .welcome {
      flex: 1; display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      padding: 40px 20px; gap: 16px;
    }
    .welcome h1 { font-size: 32px; font-weight: 700; color: #111827; }
    .welcome p { font-size: 14px; color: #6b7280; }

    .input-bar {
      display: flex; align-items: center; gap: 0;
      width: 100%; max-width: 640px;
      border-radius: 12px; overflow: hidden;
      border: 1px solid #d1d5db;
      background: #ffffff;
      transition: border-color 0.15s;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .input-bar:focus-within { border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.1); }

    .chat-input {
      flex: 1; padding: 12px 16px; border: none;
      background: transparent; color: #24292e;
      font-size: 14px; font-family: "Inter", system-ui, sans-serif;
      outline: none;
    }
    .chat-input::placeholder { color: #9ca3af; }
    .chat-input:disabled { opacity: 0.5; }

    .send-btn {
      padding: 12px 20px; border: none;
      background: #4f46e5; color: #ffffff;
      font-weight: 600; font-size: 13px;
      cursor: pointer; transition: all 0.15s;
    }
    .send-btn:hover { background: #4338ca; }
    .send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

    .error-text { color: #dc2626; font-size: 13px; }
    .hint { color: #9ca3af; font-size: 14px; }

    .terminal-wrap {
      flex: 1; min-height: 0; display: flex; flex-direction: column;
      margin: 8px; border-radius: 10px; overflow: hidden;
      border: 1px solid #e1e4e8;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .terminal-bar {
      display: flex; align-items: center; gap: 8px;
      padding: 6px 14px; height: 32px;
      background: #f6f8fa;
      border-bottom: 1px solid #e1e4e8;
      font-size: 12px; color: #57606a;
    }
    .dot { width: 8px; height: 8px; border-radius: 50%; }
    .dot.green { background: #2da44e; }
    .dot.yellow { background: #d4a72c; }
    .bar-label { font-weight: 600; color: #24292e; }
    .bar-session { opacity: 0.5; font-family: "JetBrains Mono", "Fira Code", monospace; font-size: 11px; }
    .terminal-body { flex: 1; min-height: 0; }
    `,
  ],
})
export class AppComponent implements OnInit {
  readonly endpoint = window.location.origin;
  readonly apiKey = "test-key-123";
  readonly darkThemes = THEME_PRESETS.filter((t) => t.dark);
  readonly lightThemes = THEME_PRESETS.filter((t) => !t.dark);
  private readonly DARK_UI_AGENTS = new Set(["claude", "codex", "gemini", "opencode"]);

  private api = new AgiApiClient(this.endpoint, this.apiKey);
  private cdr = inject(ChangeDetectorRef);
  private zone = inject(NgZone);

  tools: Record<string, ToolInfo> = {};
  availableTools: { name: string; label: string }[] = [];
  sessionId = "";
  selectedTool = "";
  selectedLabel = "";
  themeName = "light";
  currentTheme: TerminalTheme = THEME_PRESETS.find((t) => t.name === "light")!.theme;
  connected = false;
  error = "";
  launching = false;
  prompt = "";

  onAgentChange() {
    if (this.DARK_UI_AGENTS.has(this.selectedTool)) {
      this.themeName = "dark";
    } else if (this.themeName === "dark") {
      this.themeName = "light";
    }
    this.onThemeChange();
  }

  onThemeChange() {
    const entry = THEME_PRESETS.find((t) => t.name === this.themeName);
    this.currentTheme = entry?.theme ?? THEME_PRESETS[0].theme;
  }

  ngOnInit() {
    this.zone.run(() => {
      this.api.listTools().then((tools) => {
        this.tools = tools;
        this.availableTools = Object.entries(this.tools)
          .filter(([name, info]) => info.available && name !== "bash")
          .map(([name, info]) => ({ name, label: info.label }));
        if (this.availableTools.length > 0) {
          this.selectedTool = this.availableTools[0].name;
          this.onAgentChange();
        }
        this.cdr.detectChanges();
      }).catch((e: any) => {
        this.error = e.message;
        this.cdr.detectChanges();
      });
    });
  }

  submit() {
    if (this.launching || !this.selectedTool) return;
    this.launching = true;
    this.error = "";
    this.api.createSession({
      user_id: "demo-user",
      tool: this.selectedTool,
      sandbox: true,
      label: this.tools[this.selectedTool]?.label ?? this.selectedTool,
      prompt: this.prompt || undefined,
    }).then((session) => {
      this.sessionId = session.session_id;
      this.selectedLabel = this.tools[this.selectedTool]?.label ?? this.selectedTool;
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

  onConnect() {
    this.connected = true;
    this.cdr.detectChanges();
  }

  onDisconnect() {
    this.connected = false;
    this.cdr.detectChanges();
  }
}
