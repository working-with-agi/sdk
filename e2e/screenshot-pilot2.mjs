import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

page.on("console", msg => console.log(`[browser] ${msg.type()}: ${msg.text()}`));
page.on("pageerror", err => console.log(`[browser error] ${err.message}`));

await page.goto("http://localhost:5199/");
await page.waitForTimeout(2000);

const bashBtn = page.locator("button", { hasText: "Bash Shell" });
await bashBtn.click();
await page.waitForTimeout(4000);

// Check DOM structure
const html = await page.evaluate(() => document.querySelector('.pilot-area')?.innerHTML?.slice(0, 500));
console.log("pilot-area HTML:", html);

await page.screenshot({ path: "/tmp/pilot2.png" });
console.log("Done");
await browser.close();
