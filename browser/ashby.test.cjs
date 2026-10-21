"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { validateManifest } = require("./ashby.cjs");
const { choiceValue } = require("./ashby.cjs");

const controls = [
  { index: 0, label: "Name", kind: "text", required: true },
  { index: 1, label: "Resume", kind: "file", required: true },
  { index: 2, label: "Do you have work authorization to work in that country?", kind: "choice", required: true, choices: ["yes", "no"] },
];
const manifest = { fields: [
  { label: "Name", value: "Test Candidate", source: "user_supplied" },
  { label: "Resume", value: "/tmp/example.pdf", source: "user_supplied" },
  { label: controls[2].label, value: "Yes", source: "user_supplied" },
] };

test("complete exact manifest passes prefill validation", () => {
  assert.equal(validateManifest(controls, manifest), true);
});
test("missing or unexpected form questions block all filling", () => {
  assert.throws(() => validateManifest(controls, { fields: manifest.fields.slice(0, 2) }), /required answer missing/);
  assert.throws(() => validateManifest([...controls, { index: 3, label: "Surprise", kind: "unknown" }], manifest), /unsupported/);
  assert.throws(() => validateManifest(controls, { fields: [...manifest.fields, { label: "Extra", value: "x", source: "user_supplied" }] }), /form changed/);
});
test("invalid yes-no choice and unresolved answers block", () => {
  assert.throws(() => validateManifest(controls, { fields: manifest.fields.map(f =>
    f.label === controls[2].label ? { ...f, value: "Maybe" } : f) }), /invalid answer/);
  assert.throws(() => validateManifest(controls, { ...manifest, unresolved: ["missing fact"] }), /unresolved/);
});

test("Swedish answers map to actual yes/no DOM values", () => {
  assert.equal(choiceValue(controls[2], "Ja"), "yes");
  assert.equal(choiceValue(controls[2], "Nej"), "no");
  assert.equal(validateManifest(controls, { fields: manifest.fields.map(f =>
    f.label === controls[2].label ? { ...f, value: "Ja" } : f) }), true);
});

test("textarea and omitted optional fields validate without fabricated answers", () => {
  assert.equal(validateManifest([...controls, { label: "Optional note", kind: "textarea", required: false }], manifest), true);
});
