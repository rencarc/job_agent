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

The CLI has no model provider and cannot spend model credits. `run_pipeline`
exposes an optional evaluator interface for later provider integration; that
interface can annotate priority only, never clear eligibility exceptions or
enable submission. A future adapter must enforce the provided token maximum at
the provider boundary and a request timeout. No such adapter is enabled here.

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

## Remaining integration, in order

1. Confirm the real profile and field mapping; inspect one live read-only run.
2. Label representative jobs and calibrate the selection baseline. Add a bounded
   semantic evaluator only where measured improvements justify its token cost.
3. Verify posting liveness, choose the actual CV, reuse approved answers, compile
   and inspect materials, then connect preparation tasks to browser manifests.
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
