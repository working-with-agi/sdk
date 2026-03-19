import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

await page.goto("http://localhost:5199/");
await page.waitForTimeout(2000);

// Screenshot: landing page
await page.screenshot({ path: "/tmp/float-landing.png" });
console.log("1. Landing captured");

// Launch Bash in float mode
const bashBtn = page.locator("button", { hasText: "Bash Shell" });
await bashBtn.click();
await page.waitForTimeout(3000);
await page.screenshot({ path: "/tmp/float-dark.png" });
console.log("2. Float dark captured");

// Toggle theme to light
const themeBtn = page.locator(".theme-btn");
await themeBtn.click();
await page.waitForTimeout(1000);
await page.screenshot({ path: "/tmp/float-light.png" });
console.log("3. Float light captured");

await browser.close();
console.log("Done");
