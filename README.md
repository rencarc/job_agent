# Auditable Job Agent

## Incremental automatic selection

The new bounded runner saves jobs and JD versions in SQLite, reuses unchanged
evaluations, checks tracker history on every run, and automatically creates
preparation tasks or exceptions. Discovery, caching and profile-rule matching
use **zero LLM calls**. See [docs/AUTOMATION.md](docs/AUTOMATION.md) for setup,
limits, recovery behavior, and what remains to be integrated.

```bash
python -m job_agent.run_cli --settings data/search_settings.example.json --profile private/automation_profile.json
```

Create the private profile from `data/automation_profile.example.json`, replace
all sample facts, and confirm the actual profile before use. Live runs require
`AIRTABLE_TOKEN`, `AIRTABLE_BASE_ID` and `AIRTABLE_TABLE_ID`. History fields may
use names or field IDs consistently; a mixed core mapping is rejected.

This release queues preparation tasks; it does not generate tailored documents,
enable a model provider, install a schedule, send notifications, or submit forms.

For read-only draft-profile validation, add `--preview` and an explicitly separate
`--db private/preview.sqlite`. Optional `--resume-catalog PRIVATE_CATALOG` creates
local preparation plans referencing reviewed CV bytes and supported facts. It
does not rewrite the CV, generate a cover letter by default, or submit anything.

An evidence-first job discovery, scoring, and application-audit toolkit.

The project focuses on low-risk automation:

- discover recent jobs from supported public sources;
- normalize jobs into a shared model;
- deduplicate by ATS identity, canonical URL, and content fingerprint;
- score jobs with explainable evidence;
- keep safety defaults in shadow mode;
- require human review for hard blockers, ambiguous eligibility questions, login/CAPTCHA, and unclear submission states;
- sync only verified application receipts to an external tracker.

## Safety Defaults

```text
SHADOW_MODE=true
AUTO_REJECT=false
AUTO_SUBMIT=false
```

Scores are priority signals, not permission to submit. A job can only be marked `Applied` after an authoritative confirmation receipt is recorded.

## What Is Included

- Python job-agent modules under `job_agent/`
- source adapters for JobTech and public ATS boards
- application ledger and receipt checks
- browser inspection helpers under `browser/`
- example configuration under `data/`
- unit tests under `tests/`

Private files are intentionally excluded:

- applicant profiles
- browser profiles and cookies
- CV PDFs and cover letters
- real application receipts
- local output reports
- API tokens and `.env` files

## Run Tests

```bash
python -m unittest discover -s tests -q
node --test browser/ashby.test.cjs
```

## Discovery Examples

```bash
python -m job_agent.discover_cli --limit 10
python -m job_agent.discover_cli --recent-days 7 --jobtech-pages 3
python -m job_agent.discover_cli --settings data/search_settings.example.json
python -m job_agent.discover_cli --settings data/search_settings.24h.example.json
```

Optional tracker sync uses an environment variable:

```bash
AIRTABLE_TOKEN=... python -m scripts.daily_scan --settings data/search_settings.example.json
```

Never commit tokens, private profiles, browser sessions, CVs, or receipts.

## Browser Inspection

Browser helpers are designed for local, auditable runs. They should inspect and preview forms before any submission logic is added.

```bash
npm install
npx playwright install chromium
node browser/ashby_cli.cjs inspect URL private/inspection.json
```

After building a manifest, `preview URL manifest.json output.json` now opens a
visible browser and keeps it open until you close it. `--audit-only` retains the
headless, close-after-readback behavior for explicit audit runs. A preview audit
does not prove that a submission occurred and never updates Applied status.

The default output paths point to `private/`, which is ignored by git.

## Development Notes

This repository is a cleaned public release. Runtime outputs and user-specific application history are not part of the source tree. Add new ATS adapters behind tests and preserve the rule that uncertain state pauses for human review.
