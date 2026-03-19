import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

await page.goto("http://localhost:5199/");
await page.waitForTimeout(2000);

// Launch Bash
const bashBtn = page.locator("button", { hasText: "Bash Shell" });
await bashBtn.click();
await page.waitForTimeout(3000);

// Type some text so we can see the theme difference
const terminal = page.locator(".float-body");
await terminal.click();
await page.keyboard.type("echo hello world && ls /", { delay: 30 });
await page.keyboard.press("Enter");
await page.waitForTimeout(1500);
await page.screenshot({ path: "/tmp/theme2-dark.png" });
console.log("1. Dark with content");

// Toggle to light
await page.locator(".theme-btn").click();
await page.waitForTimeout(1000);
await page.screenshot({ path: "/tmp/theme2-light.png" });
console.log("2. Light with content");

await browser.close();
