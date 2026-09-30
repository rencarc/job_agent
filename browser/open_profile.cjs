"use strict";

const path = require("node:path");
const fs = require("node:fs");
const { chromium } = require("playwright");

function findChromeExecutable() {
  const explicit = process.env.CHROME_PATH;
  const candidates = [
    explicit,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, "Google\\Chrome\\Application\\chrome.exe")
      : null,
  ].filter(Boolean);

  return candidates.find(candidate => fs.existsSync(candidate));
}

async function main(args) {
  const url = args[0] || "https://example.com";
  const profileDir = path.resolve(process.env.JOB_AGENT_CHROME_PROFILE || "private/chrome-profile-job-agent");
  const executablePath = findChromeExecutable();
  if (!executablePath) {
    throw new Error("Google Chrome was not found. Set CHROME_PATH to chrome.exe and try again.");
  }

  const context = await chromium.launchPersistentContext(profileDir, {
    executablePath,
    headless: false,
    viewport: { width: 1365, height: 900 },
    acceptDownloads: true,
  });
  const page = context.pages()[0] || await context.newPage();
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  process.stdout.write(`Opened Google Chrome with the dedicated job-automation profile:\n${profileDir}\n${page.url()}\n`);
  process.stdout.write("Log in manually if needed. Close the browser window when you are done.\n");
  await new Promise(resolve => context.on("close", resolve));
}

if (require.main === module) {
  main(process.argv.slice(2)).catch(error => {
    process.stderr.write(`Could not open browser profile: ${error.message}\n`);
    process.exitCode = 1;
  });
}
