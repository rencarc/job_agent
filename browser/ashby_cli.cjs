"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { inspectAshby, fillAshbyPreview } = require("./ashby.cjs");

async function main(args) {
  const auditOnly = args.includes("--audit-only");
  if (args.some(arg => arg.startsWith("--") && arg !== "--audit-only")) throw new Error("unknown option");
  const [mode, url, manifestPath, outputPath] = args.filter(arg => arg !== "--audit-only");
  if (!["inspect", "preview"].includes(mode)) throw new Error("usage: node browser/ashby_cli.cjs inspect URL [output.json] OR preview URL manifest.json output.json");
  const parsed = new URL(url);
  if (parsed.protocol !== "https:" || parsed.hostname !== "jobs.ashbyhq.com" || !parsed.pathname.endsWith("/application")) {
    throw new Error("only a direct Ashby application URL is supported");
  }
  if (mode === "preview" && (!manifestPath || !outputPath)) throw new Error("preview requires manifest and private output paths");
  const playwright = require("playwright");
  const browser = await playwright.chromium.launch({ headless: mode === "inspect" || auditOnly });
  try {
    const page = await browser.newPage();
    await page.goto(parsed.href, { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.locator(".ashby-application-form-field-entry").first().waitFor({ timeout: 30000 });
    if (mode === "inspect") {
      const controls = await inspectAshby(page);
      const serialized = JSON.stringify({ url: page.url(), controls }, null, 2) + "\n";
      if (manifestPath) {
        fs.mkdirSync(path.dirname(path.resolve(manifestPath)), { recursive: true });
        fs.writeFileSync(manifestPath, serialized, { mode: 0o600 });
      }
      else process.stdout.write(serialized);
      return;
    }
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    if (manifest.url !== page.url()) throw new Error("manifest URL differs from the current employer form");
    const observed = await fillAshbyPreview(page, manifest);
    const target = path.resolve(outputPath);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, JSON.stringify({ url: page.url(), submitted: false,
      selected_cv: manifest.selected_cv, resume_sha256: manifest.resume_sha256,
      filled_at: new Date().toISOString(), fields: observed }, null, 2) + "\n", { mode: 0o600 });
    process.stdout.write(`Preview filled and locally audited: ${target}\n`);
    // Intentionally no click on Submit Application in preview mode.
    if (!auditOnly) {
      process.stdout.write("The filled browser stays open for your review. Close it when finished. Submission is not recorded automatically.\n");
      await new Promise(resolve => browser.once("disconnected", resolve));
    }
  } finally {
    if (browser.isConnected()) await browser.close();
  }
}

if (require.main === module) main(process.argv.slice(2)).catch(error => {
  process.stderr.write(`Ashby adapter stopped: ${error.message}\n`);
  process.exitCode = 1;
});

module.exports = { main };
