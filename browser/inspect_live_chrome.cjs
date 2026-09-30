"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

async function visibleTexts(locator, limit = 30) {
  const items = [];
  const count = Math.min(await locator.count(), limit);
  for (let index = 0; index < count; index += 1) {
    const item = locator.nth(index);
    if (!(await item.isVisible().catch(() => false))) continue;
    const text = (await item.innerText().catch(() => "")).replace(/\s+/g, " ").trim();
    if (text) items.push(text.slice(0, 200));
  }
  return items;
}

async function visibleControls(page) {
  return page.evaluate(() => {
    const isVisible = element => {
      const style = window.getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return style.visibility !== "hidden" && style.display !== "none" && box.width > 0 && box.height > 0;
    };
    const labelFor = element => {
      const id = element.getAttribute("id");
      const aria = element.getAttribute("aria-label") || element.getAttribute("aria-labelledby");
      const name = element.getAttribute("name");
      const placeholder = element.getAttribute("placeholder");
      const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`)?.textContent : "";
      return (label || aria || placeholder || name || "").replace(/\s+/g, " ").trim();
    };
    return Array.from(document.querySelectorAll("input, textarea, select"))
      .filter(isVisible)
      .map((element, index) => ({
        index,
        tag: element.tagName.toLowerCase(),
        type: element.getAttribute("type") || element.tagName.toLowerCase(),
        label: labelFor(element),
        required: element.required || element.getAttribute("aria-required") === "true",
        value: element.type === "password" ? "<password>" : element.value || "",
      }));
  });
}

async function main(args) {
  const [url, outputPath = "private/live_chrome_probe.json", endpoint = "http://127.0.0.1:9222"] = args;
  if (!url || !/^https:\/\//i.test(url)) {
    throw new Error("usage: node browser/inspect_live_chrome.cjs HTTPS_URL [output.json] [debug-endpoint]");
  }
  const browser = await chromium.connectOverCDP(endpoint);
  try {
    const context = browser.contexts()[0] || await browser.newContext();
    let page = context.pages().find(candidate => candidate.url().includes("successfactors.eu")) ||
      context.pages().find(candidate => candidate.url() !== "about:blank") ||
      await context.newPage();
    if (!page.url().includes("successfactors.eu")) {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
      await page.waitForTimeout(1500);
    }
    const snapshot = {
      input_url: url,
      final_url: page.url(),
      title: await page.title(),
      captured_at: new Date().toISOString(),
      headings: await visibleTexts(page.locator("h1, h2, h3")),
      buttons: await visibleTexts(page.getByRole("button")),
      links: await visibleTexts(page.getByRole("link")),
      controls: await visibleControls(page),
      text_sample: (await page.locator("body").innerText().catch(() => "")).replace(/\s+/g, " ").trim().slice(0, 5000),
    };
    const target = path.resolve(outputPath);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, JSON.stringify(snapshot, null, 2) + "\n", { mode: 0o600 });
    process.stdout.write(`Live Chrome inspection saved: ${target}\n`);
    process.stdout.write(`Final URL: ${snapshot.final_url}\n`);
    process.stdout.write(`Visible controls: ${snapshot.controls.length}\n`);
  } finally {
    await browser.close();
  }
}

if (require.main === module) {
  main(process.argv.slice(2)).catch(error => {
    process.stderr.write(`Live Chrome inspection stopped: ${error.message}\n`);
    process.exitCode = 1;
  });
}
