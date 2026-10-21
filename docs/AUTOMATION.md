# Bounded automatic selection

## Implemented scope

This change is the first implementation of the economical automation plan:

1. Read JobTech and configured public ATS boards without an LLM.
2. Preserve successful queries/pages when another query fails.
3. Save stable posting identities, aliases, original snapshots and content versions.
4. Match new/changed postings against verified, structured career facts.
5. Reuse the evaluation when job content, profile and rule version are unchanged.
6. Recheck Airtable application history even when matching is cached.
7. Route to `prepare`, `exception`, `skip` or `deferred` automatically.
8. Save progress and usage before exporting a JSON handoff.

`prepare` means **prepare application materials**, not ready/authorized to submit.
All tasks have `can_submit: false`. Posting liveness is explicitly `unverified`.
The current matcher is a conservative rule baseline, not a calibrated semantic
model or a probability of success. Language levels and work-eligibility clauses
still become exceptions. It does not infer work authorization from a language or
country preference.

### Draft-profile preview and location preferences

`--preview` accepts a structurally valid, unconfirmed profile for read-only
evaluation. It skips Airtable reads, never invokes a model, and exports only
`preview` tasks with separate `suggested_decision` and `routing_decision` fields.
It requires an explicitly separate database; databases are bound to preview or
production mode so a draft cannot overwrite the production queue. Suggestions
are ranked by decision, preferred location and rule priority. Other Swedish
cities remain candidates: `preferred_locations` changes ordering, not eligibility.
An explicit city in a staffing-ad title takes ranking precedence over an agency's
structured location. This is a heuristic, not verified workplace geocoding.

Optional `language_levels` distinguishes known fluent English from intermediate
Swedish; missing levels are not invented. The rule parser separates required,
preferred/negated and merely mentioned languages, retains quotes, and flags gaps.
It is not a complete natural-language parser. `technical_seniority: early_career`
flags senior technical titles and explicit multi-year technical requirements for
review instead of treating business-operations tenure as engineering experience.
`skill_aliases` can match spellings such as PowerApps without counting aliases as
multiple separate skills. Scores are rule priorities, not match probabilities.

Explicit required technology sections retain unsupported-skill quotes for
review; the parser does not turn a missing CV mention into a claim of inability.
Numeric and common written year counts, production ownership wording and senior
roles stated inside a description are also review signals for an early-career
profile. These checks remain heuristic and need independent evaluation labels.

JobTech publication deadlines and removal status are retained. Deadline/removal
checks run again even when matching is cached; an elapsed structured deadline
suppresses preparation. Conflicting body/structured deadlines become exceptions,
because a repost may retain stale text. This is not an employer-site liveness
check. Local deadline dates use Europe/Stockholm; Windows installs the small
`tzdata` runtime dependency for IANA timezone support.

Keep the real profile/CV under ignored private storage. If `source_document` and
`source_sha256` are present, both are required and the source hash is checked
before a run; a changed CV requires re-reviewing its derived facts. Never publish
real candidate facts as test fixtures. A preview can validate data flow and find
regressions, but it cannot establish precision/recall without independent labels.

```text
python -m job_agent.run_cli --settings PRIVATE_SETTINGS --profile PRIVATE_DRAFT --preview --db private/preview.sqlite --max-requests 12
```

The CLI has no model provider and cannot spend model credits. `run_pipeline`
exposes an optional evaluator interface for later provider integration; that
interface can annotate priority only, never clear eligibility exceptions or
enable submission. A future adapter must enforce the provided token maximum at
the provider boundary and a request timeout. No such adapter is enabled here.

### Preparation plans and scoped eligibility answers

`--resume-catalog PRIVATE_CATALOG` reuses an existing reviewed PDF and writes a
local preparation plan for each `prepare` candidate (or suggested candidate in
preview). Start from `data/preparation_catalog.example.json`. A catalog records
CV paths, reviewed SHA-256 hashes, focus terms and supporting fact IDs. The CV is
checked before scanning and again when planning; the plan never modifies the
PDF or invents an experience claim. Plans retain unresolved fields, do not
generate a cover letter by default, and cannot submit. Replays reuse the same
plan identity and refuse to overwrite conflicting user edits.

The catalog's PDF header/hash checks establish identity with a previously
reviewed file, not a complete PDF validity/layout check. Human document review
and downstream form readback remain required parts of integration.

Each CLI task and preparation plan includes an `application_route`. This
zero-request classifier distinguishes the supported Ashby preview route from
other providers, unknown forms, company homepages and insecure endpoints.
Teamtailor-style custom-domain paths are marked as hints requiring their own
adapter; they never reuse the Ashby driver. Route support does not establish
posting openness or permission to submit. Mandatory CI/CD and version-control
requirements also retain unsupported-profile evidence for review.

Eligibility distinguishes current work authorization, employer support now,
and employer support in the future. A known future support requirement permits
`Yes` to a now-or-future sponsorship question, but does not invent an answer to
a current-only question or imply permanent/unrestricted work authorization.
Optional `employer_support_required_now` and `employer_support_required_future`
fields can remain null. Unknown timeframe questions pause for review. Older
combined profiles remain supported for their original unsplit question scope.

## Configure once

Copy `data/automation_profile.example.json` to `private/automation_profile.json`.
Replace sample facts with confirmed career claims, map skill terms to their
supporting fact IDs, choose target role phrases/languages, and only then set
`confirmed_by_user` to true. The example is intentionally not executable as a
confirmed real profile. Keep personal data under ignored `private/`.

Use existing search settings. For a live history read set:

- `AIRTABLE_TOKEN`
- `AIRTABLE_BASE_ID`
- `AIRTABLE_TABLE_ID`
- Relevant `AIRTABLE_FIELD_*` overrides, if the tracker does not use the default names.

The four history fields (`company`, `role`, `job_link`, `status`) must use either
names or IDs consistently. ID mode requests ID-keyed records; name mode requests
name-keyed records. API failures do not become an empty history. No tracker
records are created or updated by automatic selection.

If an existing application ledger is used, pass its exact path with
`--application-ledger PRIVATE_LEDGER`. It is read in SQLite read-only mode before
scanning. Missing, corrupt or unknown-state ledgers stop the run rather than
pretending there is no prior application. Submitted/synced entries suppress
selection; unresolved claims route to review before any model dispatch.
Both posting URLs and scoped ATS identities are checked, including Ashby's
posting/application URL variants. The fence also applies to preview material
plans and cached matches. An empty local ledger does not establish that external
history is empty. This per-run snapshot cannot replace the atomic claim/check
immediately before any future submit driver; it does not implement that driver.

```text
python -m job_agent.run_cli --settings data/search_settings.example.json --profile private/automation_profile.json
```

The database defaults to `private/job_agent.sqlite`. Results go to
`output/automation/latest.json` and timestamped run/coverage files. Each task
includes the original posting, evidence fact IDs and routing reasons. `skip`
records remain in SQLite and are inspectable; they are not deleted.

The existing `python -m scripts.daily_scan` also supports `--profile` and `--db`.
Without `--profile` it keeps the legacy discovery-only behavior. This change does
not install a timer: choose a schedule after validating the actual profile and
one live read-only run. Do not configure both old and new invocations together.

## Limits and recovery

Defaults per invocation:

| Bound | Default | Behavior when reached |
|---|---:|---|
| Public-source HTTP attempts, including retries | 120 | Keep success, mark source incomplete |
| Public-source scan time | 180 seconds | Stop dispatching further reads |
| Evaluations | 30 | Save remaining jobs as deferred |
| Evaluation-stage time | 120 seconds | Save remaining jobs as deferred |
| Enabled model calls/tokens | 0 / 0 | CLI never invokes a model |

CLI overrides: `--max-requests`, `--scan-seconds`, `--max-evaluations`,
`--evaluation-seconds`. Source HTTP reads have at most one retry, only on
transient errors; retries count toward the same request allowance. Retry-After
is honored or deferred when it exceeds the remaining time. Reads have a
per-request timeout and an 8 MiB response limit. Scan deadlines stop further
dispatch but an in-flight socket read may finish after the nominal deadline;
the legacy daily wrapper caps its new child at 600 seconds. Airtable history
reads are separate from the public-source request allowance.

Page responses are committed to the database as they arrive. An interrupted
scan keeps its original cutoff and batch ID: rerunning reuses completed pages
and spends its HTTP allowance on the remaining pages. Once every source has a
terminal result, the next batch uses a fresh namespace and refetches the feeds.
`truncated` is terminal for a configured source cap but is always reported as
partial coverage; increasing limits/settings is necessary for more coverage.
An unfinished batch older than seven days stops with an actionable error rather
than silently abandoning never-scanned sources. Old batches/versions are retained
for audit; a retention/cleanup policy remains future work.

Jobs are ingested before declaring a scan complete. Evaluations and queue
updates are committed individually, so a process failure resumes from durable
jobs/cache. A crash between caching and queue update is repaired on the next
run. Leases reject overlapping scans; a crashed invocation's lease expires after
the configured stage budgets plus a grace period. Scheduling should allow for
that recovery interval rather than force-starting a second worker.

The optional library evaluator reserves the **maximum** call tokens atomically
against the UTC day's durable allowance before dispatch. A successful response
settles to reported actual use. Failed/uncertain calls keep their reservation;
restarting does not refund them. Call count does not reset on restart. The
model/prompt version is mandatory in its cache key. These are tested library
controls, not a claim that a provider integration is already deployed.

## Offline verification

```text
python -m unittest discover -s tests -q
node --test browser/ashby.test.cjs
python -m job_agent.run_cli --settings data/search_settings.example.json --profile PRIVATE_CONFIRMED_PROFILE --offline-jobs JOBS_SNAPSHOT --db private/replay.sqlite
```

Offline replay performs no network requests. It intentionally marks history as
unverified, so eligible fixtures become exceptions rather than pretending no
previous application exists. It can prove caching/recovery, not live coverage or
real-world matching accuracy. CI runs offline Python/Node tests on Windows/Linux;
local passing tests do not establish that hosted CI or a live browser run passed.
PDF tests require pdflatex and pdftotext and skip when unavailable.

## Browser handoff

Ashby preview now remains open visibly for the user to continue. Swedish Ja/Nej
answers map to the actual yes/no option values; textarea controls are supported.
Unanswered optional supported controls can be omitted. Unknown controls still
block filling. Only one PDF upload is supported in a planned manifest.

```text
node browser/ashby_cli.cjs preview URL private/manifest.json private/readback.json
```

Use `--audit-only` only when intentionally filling headlessly and closing after
the audit. No preview path clicks submit or records an application receipt.

`scripts.plan_ashby --preparation-plan PRIVATE_PLAN` can bind a material plan
to an inspected form. It requires the same posting/ATS identity, the same CV
variant and unchanged reviewed PDF bytes. Only one explicitly labeled CV/resume
upload is auto-populated; ambiguous or cover-letter uploads stop the handoff.
The standard fields still require a confirmed private form profile. Preparation
unresolved items are retained separately in the manifest; filling a preview
does not clear history/liveness issues or grant permission to submit.

## Remaining integration, in order

1. Confirm the real profile and field mapping; inspect one live read-only run.
2. Label representative jobs and calibrate the selection baseline. Add a bounded
   semantic evaluator only where measured improvements justify its token cost.
3. Verify posting liveness and connect reviewed-CV preparation plans and approved
   scoped answers to browser manifests. Add tailoring only when useful; new PDFs
   must be compiled and inspected before use.
4. Add independently verified receipt capture and unknown-submission recovery;
   connect the existing ledger/outbox to one tested ATS.
5. Configure the approved ATS/role/daily submission limits before enabling any
   automatic submit driver. No submit driver exists in this release.
6. Choose a schedule and exception delivery channel after the preceding checks;
   ordinary unchanged runs should remain quiet.

Measure token usage per relevant job, p50/p95 run duration, exception rate,
precision@10 and missed relevant postings on held-out human labels. This release
does not assert that a percentage accuracy, production latency or end-to-end
submission success target has already been reached.
