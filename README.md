# Auditable Job Agent

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

The default output paths point to `private/`, which is ignored by git.

## Development Notes

This repository is a cleaned public release. Runtime outputs and user-specific application history are not part of the source tree. Add new ATS adapters behind tests and preserve the rule that uncertain state pauses for human review.
