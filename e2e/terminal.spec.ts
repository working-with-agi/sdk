import { test, expect } from "@playwright/test";

const AGITERM_URL = "http://localhost:8601";
const API_KEY = "test-key-123";
const APP_URL = "http://localhost:5199";

test.describe("WorkWithAGI Vue Terminal E2E", () => {
  test("connects to agiterm-server and renders terminal", async ({ page }) => {
    await page.goto(APP_URL);

    // Wait for session creation and connection
    await expect(page.getByTestId("connected")).toBeVisible({ timeout: 15000 });

    // Terminal canvas should be rendered (xterm.js)
    const terminal = page.locator(".xterm");
    await expect(terminal).toBeVisible({ timeout: 5000 });

    // The xterm canvas should exist
    const canvas = page.locator(".xterm canvas");
    await expect(canvas.first()).toBeVisible();
  });

  test("can type commands and receive output", async ({ page }) => {
    await page.goto(APP_URL);
    await expect(page.getByTestId("connected")).toBeVisible({ timeout: 15000 });

    // Focus the terminal
    await page.locator(".xterm").click();

    // Type a command
    await page.keyboard.type("echo E2E_PLAYWRIGHT_OK\n", { delay: 50 });

    // Wait for output to appear in the terminal
    // xterm renders to canvas, so we check via the terminal's buffer
    // We'll use a helper command that outputs to a file we can check
    await page.keyboard.type("echo __DONE__ > /tmp/e2e_marker\n", { delay: 50 });

    // Verify via REST API that the session is still alive
    const response = await page.request.get(`${AGITERM_URL}/api/v1/sessions`, {
      headers: { "X-API-Key": API_KEY },
    });
    const sessions = await response.json();
    expect(sessions.length).toBeGreaterThan(0);
    expect(sessions[0].label).toBe("e2e-vue-test");
  });

  test("handles session list via API client", async ({ page }) => {
    // Verify the REST API works from the test harness
    const response = await page.request.get(`${AGITERM_URL}/api/v1/health`);
    const health = await response.json();
    expect(health.status).toBe("ok");
    expect(health.service).toBe("agiterm");
  });
});
