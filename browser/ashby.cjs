"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

/** Read only fields actually rendered by the employer's Ashby form. */
async function inspectAshby(page) {
  return page.evaluate(() => Array.from(document.querySelectorAll(".ashby-application-form-field-entry"))
    .map((entry, index) => {
      const title = entry.querySelector("label.ashby-application-form-question-title");
      const input = entry.querySelector("input:not([type=hidden]), textarea, select");
      const choices = entry.querySelector(".ashby-application-form-input-yesno");
      const kind = choices ? "choice" : input?.type === "file" ? "file" :
        input?.tagName === "TEXTAREA" ? "textarea" :
        ["text", "email", "url"].includes(input?.type) ? input.type : "unknown";
      return { index, label: title?.textContent?.trim() || "", required: Boolean(title?.className?.includes("_required_")),
        kind, choices: choices ? Array.from(choices.querySelectorAll("button[data-option]"), b => b.dataset.option) : [] };
    }));
}

function choiceValue(control, value) {
  const raw = String(value).trim().toLowerCase();
  const mapped = ({ ja: "yes", nej: "no" })[raw] || raw;
  if (control.choices.includes(raw)) return raw;
  if (control.choices.includes(mapped)) return mapped;
  return null;
}

/** Fail closed before interacting with any form control. */
function validateManifest(controls, manifest) {
  if (!manifest || !Array.isArray(manifest.fields) || !manifest.fields.length) {
    throw new Error("a nonempty audited field manifest is required");
  }
  const labels = new Set();
  const supplied = new Set();
  for (const field of manifest.fields) {
    if (supplied.has(field.label)) throw new Error(`duplicate manifest answer: ${field.label}`);
    supplied.add(field.label);
  }
  if (!controls.length) throw new Error("Ashby form has no visible fields");
  for (const control of controls) {
    if (!control.label || control.kind === "unknown") throw new Error(`unsupported control: ${control.label || control.index}`);
    if (labels.has(control.label)) throw new Error(`ambiguous duplicate label: ${control.label}`);
    labels.add(control.label);
    const field = manifest.fields.find(item => item.label === control.label);
    if (!field && control.required) throw new Error(`required answer missing: ${control.label}`);
    if (field && (typeof field.value !== "string" || !field.value.trim() || !field.source || (control.kind === "choice" &&
        choiceValue(control, field.value) === null))) throw new Error(`invalid answer: ${control.label}`);
  }
  for (const field of manifest.fields) {
    if (!labels.has(field.label)) throw new Error(`form changed or field missing: ${field.label}`);
  }
  if (manifest.unresolved?.length) throw new Error("unresolved questions block filling");
  return true;
}

/** Fill a validated manifest; never clicks Submit Application. */
async function fillAshbyPreview(page, manifest) {
  const controls = await inspectAshby(page);
  validateManifest(controls, manifest);
  if (!manifest.selected_cv || !/^[a-f0-9]{64}$/.test(manifest.resume_sha256 || "")) {
    throw new Error("selected CV id and PDF hash are required");
  }
  for (const control of controls) {
    if (control.kind !== "file") continue;
    const field = manifest.fields.find(item => item.label === control.label);
    if (!field) continue;
    const file = path.resolve(field.value);
    if (!fs.existsSync(file) || !fs.statSync(file).isFile() || path.extname(file).toLowerCase() !== ".pdf") {
      throw new Error(`resume must be an existing PDF: ${control.label}`);
    }
    if (crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex") !== manifest.resume_sha256) {
      throw new Error("resume PDF changed after approval");
    }
  }
  const root = page.locator(".ashby-application-form-field-entry");
  for (const control of controls) {
    const field = manifest.fields.find(item => item.label === control.label);
    if (!field) continue;
    const entry = root.nth(control.index);
    if ((await entry.locator("label.ashby-application-form-question-title").textContent()).trim() !== control.label) {
      throw new Error(`form changed while filling: ${control.label}`);
    }
    if (control.kind === "choice") {
      const value = choiceValue(control, field.value);
      if (!["yes", "no", "ja", "nej"].includes(value)) throw new Error("unsupported choice value");
      await entry.locator(`button[data-option="${value}"]`).click();
    } else if (control.kind === "file") {
      const file = path.resolve(field.value);
      await entry.locator("input[type=file]").setInputFiles(file);
    } else {
      await entry.locator(control.kind === "textarea" ? "textarea" : `input[type="${control.kind}"]`).fill(field.value);
    }
  }
  const observed = await page.evaluate(() => Array.from(document.querySelectorAll(".ashby-application-form-field-entry"))
    .map(entry => ({ label: entry.querySelector("label.ashby-application-form-question-title")?.textContent?.trim(),
      value: entry.querySelector(".ashby-application-form-input-yesno button[aria-pressed=true]")?.dataset.option ||
        entry.querySelector("input[type=file]")?.files?.[0]?.name ||
        entry.querySelector("input:not([type=file]), textarea, select")?.value || "" })));
  for (const control of controls) {
    const field = manifest.fields.find(item => item.label === control.label);
    if (!field) continue;
    const actual = observed.find(item => item.label === control.label)?.value;
    const expected = control.kind === "file" ? path.basename(field.value) :
      control.kind === "choice" ? choiceValue(control, field.value) : field.value;
    if (actual !== expected) throw new Error(`filled value could not be verified: ${control.label}`);
  }
  return observed.map(item => ({ ...item, source: manifest.fields.find(f => f.label === item.label)?.source || "" }));
}

module.exports = { inspectAshby, validateManifest, fillAshbyPreview, choiceValue };
