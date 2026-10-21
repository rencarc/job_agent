"use strict";
const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { inspectTeamtailor } = require("./teamtailor.cjs");
let playwright;
try { playwright = require("playwright"); } catch {}
const executablePath = process.env.JOB_AGENT_BROWSER_EXECUTABLE;
const available = Boolean(playwright && executablePath && fs.existsSync(executablePath));
let browser;
before(async () => {
  if (available) browser = await playwright.chromium.launch({executablePath, headless: true});
});
after(async () => {if (browser) await browser.close();});
const fixture = `<form id="job-application-form">
  <input type="hidden" name="authenticity_token" value="never-export-me">
  <div data-question-mandatory="true"><label for="m">Motivering<sup data-asterisk="true">*</sup><span class="sr-only">Obligatoriskt</span></label><textarea id="m" name="motivation"></textarea></div>
  <div data-question-mandatory="true"><label for="d">Tidigast tillgänglig?</label><input type="date" id="d" name="available"></div>
  <label for="s">Monthly salary<sup data-asterisk="true">*</sup></label><input type="number" id="s" name="salary">
  <fieldset><legend>Meet required skills?<sup data-asterisk="true">*</sup></legend>
    <input type="radio" id="dynamic-yes" name="requirements" value="true"><label for="dynamic-yes">Ja</label>
    <input type="radio" id="dynamic-no" name="requirements" value="false"><label for="dynamic-no">Nej</label></fieldset>
  <label for="cv">CV<span class="sr-only">Obligatoriskt</span></label><input type="file" id="cv">
  <label for="extra">Other documents</label><input type="file" id="extra">
  <label for="sms">SMS updates</label><input type="checkbox" id="sms" name="sms">
  <input type="submit" value="Submit">
</form>`;
async function inspect(html, verify) {
  const page = await browser.newPage();
  try {
    await page.route("**/*", route => route.abort());
    await page.setContent(html);
    await verify(page);
  } finally {await page.close();}
}
test("Teamtailor detects mandatory labels and containers without HTML required", {skip: !available}, async () => {
  await inspect(fixture, async page => {
    const before = await page.locator("#m").inputValue();
    const result = await inspectTeamtailor(page);
    assert.equal(result.controls.length, 7);
    assert.equal(result.controls.filter(c => c.required).length, 5);
    assert.deepEqual(result.controls.find(c => c.kind === "choice").choices,
      [{label:"Ja",value:"true"},{label:"Nej",value:"false"}]);
    assert.equal(result.controls.find(c => c.kind === "choice").label, "Meet required skills?");
    assert.equal(JSON.stringify(result).includes("never-export-me"), false);
    assert.equal(result.can_submit, false);
    assert.equal(await page.locator("#m").inputValue(), before);
    assert.equal(await page.locator("#sms").isChecked(), false);
  });
});
test("Teamtailor rejects unlabeled controls", {skip: !available}, async () => {
  await inspect(fixture.replace("</form>", '<input type="text" id="unknown"></form>'),
    async page => assert.rejects(inspectTeamtailor(page), /associated label/));
});
test("Teamtailor rejects ambiguous radio question", {skip: !available}, async () => {
  await inspect(fixture.replace(/<legend>[\s\S]*?<\/legend>/, ""),
    async page => assert.rejects(inspectTeamtailor(page), /ambiguous/));
});
test("Teamtailor rejects duplicate visible labels", {skip: !available}, async () => {
  await inspect(fixture.replace("Other documents", "CV"),
    async page => assert.rejects(inspectTeamtailor(page), /duplicate/));
});
test("Teamtailor does not silently discard hidden unsupported widgets", {skip: !available}, async () => {
  await inspect(fixture.replace("</form>", '<input type="text" id="invisible" style="display:none"></form>'),
    async page => assert.rejects(inspectTeamtailor(page), /unsupported/));
});
