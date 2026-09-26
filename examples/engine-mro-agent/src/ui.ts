/**
 * Planner's screen: attach to the monthly planning session and watch / steer the agent.
 *
 *   npm run build:ui && npm run serve   → http://localhost:5173/index.html?session=<session_id>
 *
 * Config comes from the page, never from the bundle:
 *   ?endpoint=https://agi.example.com:8600&session=<id>   (both optional; the form asks otherwise)
 *   API key / access token: typed into a password field and kept in memory only.
 *   In production, give the browser a short-lived Logto access token (AuthClient) instead of an API key.
 */
import { WorkAGI } from "@work-with-ai/sdk";
import type { AgiRenderedTerminal } from "@work-with-ai/sdk";

const $ = <T extends HTMLElement>(sel: string): T => {
  const el = document.querySelector<T>(sel);
  if (!el) throw new Error(`missing element ${sel}`);
  return el;
};

const form = $<HTMLFormElement>("#connect");
const endpointIn = $<HTMLInputElement>("#endpoint");
const sessionIn = $<HTMLInputElement>("#session");
const keyIn = $<HTMLInputElement>("#apikey");
const status = $<HTMLSpanElement>("#status");

const params = new URLSearchParams(location.search);
endpointIn.value = params.get("endpoint") ?? sessionStorage.getItem("wwai.endpoint") ?? "";
sessionIn.value = params.get("session") ?? "";

let term: AgiRenderedTerminal | null = null;

form.addEventListener("submit", (ev) => {
  ev.preventDefault();
  const endpoint = endpointIn.value.trim();
  const sessionId = sessionIn.value.trim();
  const apiKey = keyIn.value;
  if (!endpoint || !sessionId || !apiKey) {
    status.textContent = "endpoint / session / API key を入力してください";
    return;
  }
  try {
    sessionStorage.setItem("wwai.endpoint", endpoint); // endpoint only; never the key
  } catch {
    /* storage may be blocked */
  }

  term?.dispose();
  status.textContent = "接続中…";
  term = WorkAGI.terminal({
    container: "#terminal",
    endpoint,
    apiKey,
    sessionId,
    theme: "dark",
    fontSize: 14,
    onConnect: () => (status.textContent = `接続済み: ${sessionId}`),
    onDisconnect: () => (status.textContent = "切断されました"),
    onError: () => (status.textContent = "接続エラー（endpoint / key / session を確認）"),
  });
  keyIn.value = "";
  term.focus();
});
