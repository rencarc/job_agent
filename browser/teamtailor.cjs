"use strict";

/** Read observed fields only. Never fills, uploads, clicks or exports hidden tokens. */
function readTeamtailorForm(root) {
  const document = root || globalThis.document;
  const forms = document.querySelectorAll("#job-application-form");
  if (forms.length !== 1) throw new Error("exactly one Teamtailor application form is required");
  const form = forms[0];
  const clean = node => {
    if (!node) return "";
    const clone = node.cloneNode(true);
    clone.querySelectorAll('[data-asterisk], .sr-only').forEach(el => el.remove());
    return clone.textContent.replace(/\s+/g, " ").trim();
  };
  const visible = el => {
    const style = document.defaultView.getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden" &&
      Boolean(el.getBoundingClientRect().width && el.getBoundingClientRect().height);
  };
  const mandatory = (el, title) => Boolean(el.required || el.getAttribute("aria-required") === "true" ||
    el.closest('[data-question-mandatory="true"]') || title?.querySelector('[data-asterisk="true"]') ||
    Array.from(title?.querySelectorAll('.sr-only') || []).some(node => /^(?:Obligatoriskt|Required)$/i.test(node.textContent.trim())) ||
    /\b(?:Obligatoriskt|Required)\b/i.test(title?.textContent || ""));
  const controls = [], seenRadios = new Set();
  for (const el of form.querySelectorAll("input,textarea,select")) {
    if (["hidden", "submit", "button", "reset"].includes(el.type)) continue;
    // Do not silently lose hidden unsupported widgets or upload controls.
    if (!visible(el) && el.type !== "file") {
      controls.push({key: el.name || el.id, label: "", kind: "unknown", required: true,
        reason: "non-visible non-token control needs inspection"});
      continue;
    }
    if (el.type === "radio") {
      if (!el.name) throw new Error("radio group has no stable name");
      if (seenRadios.has(el.name)) continue;
      seenRadios.add(el.name);
      const peers = Array.from(form.querySelectorAll("input[type=radio]")).filter(p => p.name === el.name);
      const fieldset = el.closest("fieldset");
      const legend = fieldset?.querySelector("legend");
      if (!legend || peers.some(p => p.closest("fieldset") !== fieldset || !visible(p))) {
        throw new Error("radio group question or options are ambiguous");
      }
      controls.push({key: el.name, label: clean(legend), kind: "choice", required: mandatory(el, legend),
        choices: peers.map(p => ({label: clean(p.labels?.[0]), value: p.value}))});
      continue;
    }
    if (el.labels?.length !== 1) throw new Error("control needs exactly one associated label");
    const label = el.labels[0];
    const kind = el.tagName === "TEXTAREA" ? "textarea" : el.tagName === "SELECT" ? "select" :
      ["text", "email", "tel", "url", "date", "number", "file", "checkbox"].includes(el.type) ? el.type : "unknown";
    controls.push({key: el.name || el.id, label: clean(label), kind, required: mandatory(el, label)});
  }
  if (!controls.length || controls.some(c => !c.key || !c.label || c.kind === "unknown")) {
    throw new Error("unlabeled or unsupported form control needs review");
  }
  if (new Set(controls.map(c => c.key)).size !== controls.length ||
      new Set(controls.map(c => c.label)).size !== controls.length) {
    throw new Error("duplicate form identities need review");
  }
  return {provider: "teamtailor", inspection_only: true, can_submit: false, controls};
}

async function inspectTeamtailor(page) {
  return page.evaluate(readTeamtailorForm);
}

module.exports = { readTeamtailorForm, inspectTeamtailor };
