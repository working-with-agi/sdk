import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

page.on("console", msg => { if (msg.type() === "error") console.log(`[err] ${msg.text()}`); });

await page.goto("http://localhost:5199/");
await page.waitForTimeout(2000);
await page.screenshot({ path: "/tmp/pilot-landing.png" });
console.log("1. Landing");

// Launch Bash
await page.locator("button", { hasText: "Bash Shell" }).first().click();
await page.waitForTimeout(4000);
await page.screenshot({ path: "/tmp/pilot-main.png" });
console.log("2. Main terminal");

// Check toolbar exists
const toolbar = await page.locator(".toolbar").count();
console.log("Toolbar visible:", toolbar > 0);

// Dump all buttons
const buttons = await page.locator("button").allTextContents();
console.log("Buttons:", buttons);

// Add agents
if (buttons.some(b => b.includes("Developer"))) {
  await page.locator("button", { hasText: "+ Developer" }).click();
  await page.waitForTimeout(3000);
  await page.screenshot({ path: "/tmp/pilot-1agent.png" });
  console.log("3. 1 agent");

  await page.locator("button", { hasText: "+ Reviewer" }).click();
  await page.waitForTimeout(3000);
  await page.screenshot({ path: "/tmp/pilot-2agents.png" });
  console.log("4. 2 agents");
}

await browser.close();
console.log("Done");
