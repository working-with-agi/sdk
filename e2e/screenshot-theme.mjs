import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

await page.goto("http://localhost:5199/");
await page.waitForTimeout(2000);

// Launch Bash session
const bashBtn = page.locator("button", { hasText: "Bash Shell" });
await bashBtn.click();
await page.waitForTimeout(3000);
await page.screenshot({ path: "/tmp/theme-dark.png" });
console.log("1. Dark theme captured");

// Toggle to light theme
const themeBtn = page.locator(".theme-btn");
await themeBtn.click();
await page.waitForTimeout(1000);
await page.screenshot({ path: "/tmp/theme-light.png" });
console.log("2. Light theme captured");

await browser.close();
console.log("Done");
