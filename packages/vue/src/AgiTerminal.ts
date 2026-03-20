import { defineComponent, ref, onMounted, onUnmounted, watch, h } from "vue";
import { AgiRenderedTerminal } from "@work-with-ai/sdk";

export const AgiTerminal = defineComponent({
  name: "AgiTerminal",
  props: {
    endpoint: { type: String, required: true },
    apiKey: { type: String, default: undefined },
    sessionId: { type: String, default: undefined },
    theme: { type: [String, Object], default: "dark" },
    fontSize: { type: Number, default: undefined },
    fontFamily: { type: String, default: undefined },
    cursorStyle: { type: String as () => "block" | "underline" | "bar", default: undefined },
    webgl: { type: Boolean, default: true },
  },
  emits: ["output", "connect", "disconnect"],
  setup(props, { emit, expose }) {
    const containerRef = ref<HTMLElement | null>(null);
    let terminal: AgiRenderedTerminal | null = null;

    onMounted(() => {
      if (!containerRef.value) return;

      terminal = new AgiRenderedTerminal({
        container: containerRef.value,
        endpoint: props.endpoint,
        apiKey: props.apiKey,
        sessionId: props.sessionId,
        theme: props.theme as any,
        fontSize: props.fontSize,
        fontFamily: props.fontFamily,
        cursorStyle: props.cursorStyle,
        webgl: props.webgl,
        onOutput: (data) => emit("output", data),
        onConnect: () => emit("connect"),
        onDisconnect: () => emit("disconnect"),
      });
    });

    onUnmounted(() => {
      terminal?.dispose();
      terminal = null;
    });

    // Watch theme changes and apply at runtime
    watch(
      () => props.theme,
      (newTheme) => {
        if (terminal && newTheme) {
          terminal.setTheme(newTheme as any);
        }
      },
    );

    // Watch fontSize changes
    watch(
      () => props.fontSize,
      (newSize) => {
        if (terminal && newSize) {
          terminal.terminal.options.fontSize = newSize;
          terminal.fit();
        }
      },
    );

    expose({
      focus: () => terminal?.focus(),
      fit: () => terminal?.fit(),
      write: (data: string | Uint8Array) => terminal?.write(data),
    });

    return () =>
      h("div", {
        ref: containerRef,
        style: { width: "100%", height: "100%" },
      });
  },
});
