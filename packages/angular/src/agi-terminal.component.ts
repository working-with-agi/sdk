import {
  Component,
  ElementRef,
  Input,
  Output,
  EventEmitter,
  ViewChild,
  AfterViewInit,
  OnChanges,
  OnDestroy,
  SimpleChanges,
} from "@angular/core";
import { AgiRenderedTerminal } from "@work-with-ai/sdk";

@Component({
  selector: "agi-terminal",
  standalone: true,
  template: `<div #terminalContainer style="width:100%;height:100%"></div>`,
})
export class AgiTerminalComponent
  implements AfterViewInit, OnChanges, OnDestroy
{
  @ViewChild("terminalContainer") containerRef!: ElementRef<HTMLDivElement>;

  @Input({ required: true }) endpoint!: string;
  @Input() apiKey?: string;
  @Input() sessionId?: string;
  @Input() theme: "dark" | "light" | Record<string, string> = "dark";
  @Input() fontSize?: number;
  @Input() fontFamily?: string;
  @Input() cursorStyle?: "block" | "underline" | "bar";
  @Input() webgl: boolean = true;

  @Output() output = new EventEmitter<Uint8Array>();
  @Output() connected = new EventEmitter<void>();
  @Output() disconnected = new EventEmitter<void>();

  private terminal: AgiRenderedTerminal | null = null;

  ngAfterViewInit(): void {
    this.terminal = new AgiRenderedTerminal({
      container: this.containerRef.nativeElement,
      endpoint: this.endpoint,
      apiKey: this.apiKey,
      sessionId: this.sessionId,
      theme: this.theme,
      fontSize: this.fontSize,
      fontFamily: this.fontFamily,
      cursorStyle: this.cursorStyle,
      webgl: this.webgl,
      onOutput: (data) => this.output.emit(data),
      onConnect: () => this.connected.emit(),
      onDisconnect: () => this.disconnected.emit(),
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (!this.terminal) return;

    if (changes["theme"] && !changes["theme"].firstChange) {
      this.terminal.setTheme(this.theme);
    }

    if (changes["fontSize"] && !changes["fontSize"].firstChange) {
      if (this.fontSize) {
        this.terminal.terminal.options.fontSize = this.fontSize;
        this.terminal.fit();
      }
    }
  }

  ngOnDestroy(): void {
    this.terminal?.dispose();
    this.terminal = null;
  }

  focus(): void {
    this.terminal?.focus();
  }

  fit(): void {
    this.terminal?.fit();
  }

  write(data: string | Uint8Array): void {
    this.terminal?.write(data);
  }
}
