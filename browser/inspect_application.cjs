"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

function findChromeExecutable() {
  const candidates = [
    process.env.CHROME_PATH,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, "Google\\Chrome\\Application\\chrome.exe")
      : null,
  ].filter(Boolean);
  return candidates.find(candidate => fs.existsSync(candidate));
}

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

async function clickApply(page) {
  const apply = page.getByRole("button", { name: /apply/i }).or(page.getByRole("link", { name: /apply/i })).first();
  if (await apply.isVisible().catch(() => false)) {
    const popupPromise = page.waitForEvent("popup", { timeout: 10000 }).catch(() => null);
    await apply.click({ timeout: 10000 }).catch(async () => apply.click({ force: true, timeout: 10000 }));
    const popup = await popupPromise;
    if (popup) {
      await popup.waitForLoadState("domcontentloaded", { timeout: 30000 }).catch(() => {});
      await popup.bringToFront().catch(() => {});
      return popup;
    }
    await page.waitForLoadState("domcontentloaded", { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(2500);
    return page;
  }
  return page;
}

async function main(args) {
  const [url, outputPath = "private/application_probe.json", ...flags] = args;
  if (!url || !/^https:\/\//i.test(url)) throw new Error("usage: node browser/inspect_application.cjs HTTPS_URL [output.json]");
  const shouldClickApply = flags.includes("--click-apply");
  const executablePath = findChromeExecutable();
  if (!executablePath) throw new Error("Google Chrome was not found. Set CHROME_PATH to chrome.exe.");
  const profileDir = path.resolve(process.env.JOB_AGENT_CHROME_PROFILE || "private/chrome-profile-job-agent");
  const context = await chromium.launchPersistentContext(profileDir, {
    executablePath,
    headless: false,
    viewport: { width: 1365, height: 900 },
    acceptDownloads: true,
  });
  try {
    const page = context.pages()[0] || await context.newPage();
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(1500);
    const beforeClick = await page.evaluate(() => Array.from(document.querySelectorAll("button, a"))
      .filter(element => /apply/i.test(element.textContent || element.getAttribute("aria-label") || ""))
      .map(element => ({
        tag: element.tagName.toLowerCase(),
        text: (element.textContent || "").replace(/\s+/g, " ").trim(),
        href: element.getAttribute("href") || "",
        aria: element.getAttribute("aria-label") || "",
        disabled: element.disabled || element.getAttribute("aria-disabled") === "true",
        classes: element.getAttribute("class") || "",
      })));
    const activePage = shouldClickApply ? await clickApply(page) : page;
    const snapshot = {
      input_url: url,
      final_url: activePage.url(),
      title: await activePage.title(),
      clicked_apply: shouldClickApply && (activePage !== page || activePage.url() !== url),
      apply_elements_before_click: beforeClick,
      captured_at: new Date().toISOString(),
      headings: await visibleTexts(activePage.locator("h1, h2, h3")),
      buttons: await visibleTexts(activePage.getByRole("button")),
      links: await visibleTexts(activePage.getByRole("link")),
      controls: await visibleControls(activePage),
      text_sample: (await activePage.locator("body").innerText().catch(() => "")).replace(/\s+/g, " ").trim().slice(0, 4000),
    };
    const target = path.resolve(outputPath);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, JSON.stringify(snapshot, null, 2) + "\n", { mode: 0o600 });
    process.stdout.write(`Application page inspection saved: ${target}\n`);
    process.stdout.write(`Final URL: ${snapshot.final_url}\n`);
    process.stdout.write(`Visible controls: ${snapshot.controls.length}\n`);
  } finally {
    await context.close();
  }
}

if (require.main === module) {
  main(process.argv.slice(2)).catch(error => {
    process.stderr.write(`Application inspection stopped: ${error.message}\n`);
    process.exitCode = 1;
  });
}
