"use strict";
const fs = require("node:fs");
const path = require("node:path");
const { inspectTeamtailor } = require("./teamtailor.cjs");

async function main(args) {
  const [url, outputPath] = args;
  if (args.length !== 2 || !outputPath) throw new Error("usage: teamtailor_cli HTTPS_APPLICATION_URL PRIVATE_OUTPUT");
  const parsed = new URL(url);
  if (parsed.protocol !== "https:" || parsed.username || parsed.password ||
      !/^\/jobs\/\d+-[^/]+\/applications\/new\/?$/.test(parsed.pathname)) {
    throw new Error("a direct HTTPS Teamtailor-style application URL is required");
  }
  const { chromium } = require("playwright");
  const options = {headless: true};
  if (process.env.JOB_AGENT_BROWSER_EXECUTABLE) options.executablePath = process.env.JOB_AGENT_BROWSER_EXECUTABLE;
  const browser = await chromium.launch(options);
  try {
    const page = await browser.newPage();
    await page.goto(parsed.href, {waitUntil: "domcontentloaded", timeout: 30000});
    if (new URL(page.url()).origin !== parsed.origin || new URL(page.url()).pathname !== parsed.pathname) {
      throw new Error("employer application redirected; verify the destination first");
    }
    await page.locator("#job-application-form").waitFor({state: "attached", timeout: 15000});
    const inspection = {...await inspectTeamtailor(page), url: page.url(),
      captured_at: new Date().toISOString(), submitted: false};
    const target = path.resolve(outputPath);
    fs.mkdirSync(path.dirname(target), {recursive: true});
    fs.writeFileSync(target, JSON.stringify(inspection, null, 2) + "\n", {mode: 0o600});
    console.log(JSON.stringify({controls: inspection.controls.length,
      required: inspection.controls.filter(c => c.required).length, submitted: false}));
  } finally {await browser.close();}
}
if (require.main === module) main(process.argv.slice(2)).catch(error => {
  console.error("Teamtailor inspection stopped: " + error.message); process.exitCode = 1;
});
module.exports = { main };
