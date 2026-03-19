import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

await page.goto("http://localhost:5199/");
await page.waitForTimeout(2000);
await page.screenshot({ path: "/tmp/sample-landing.png" });
console.log("1. Landing page captured");

// Click Codex
const codexBtn = page.locator("button", { hasText: "OpenAI Codex CLI" });
if ((await codexBtn.count()) > 0 && (await codexBtn.isEnabled())) {
  await codexBtn.click();
  console.log("2. Clicked Codex");
  await page.waitForTimeout(6000);
  await page.screenshot({ path: "/tmp/sample-codex.png" });
  console.log("3. Codex session captured");
} else {
  const bashBtn = page.locator("button", { hasText: "Bash Shell" });
  await bashBtn.click();
  console.log("2. Clicked Bash (fallback)");
  await page.waitForTimeout(3000);
  await page.screenshot({ path: "/tmp/sample-bash.png" });
  console.log("3. Bash session captured");
}

await browser.close();
console.log("Done");
