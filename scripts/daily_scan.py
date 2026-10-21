"""One guarded scheduled scan invocation; deployment is a separate user-machine step."""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("output/daily"))
    parser.add_argument("--profile", type=Path, help="Enable durable automatic selection using a confirmed profile")
    parser.add_argument("--db", type=Path, default=Path("private/job_agent.sqlite"))
    args = parser.parse_args()
    if args.profile:
        # Keep the legacy discovery-only invocation compatible; the new path
        # scans, persists, matches, routes exceptions, and reuses cached results.
        command = [sys.executable, "-m", "job_agent.run_cli", "--settings", str(args.settings),
                   "--profile", str(args.profile), "--db", str(args.db), "--output-dir", str(args.output_dir)]
        raise SystemExit(subprocess.run(command, check=False, timeout=600).returncode)
    if not os.environ.get("AIRTABLE_TOKEN"):
        parser.error("AIRTABLE_TOKEN is required: daily runs must check Airtable history")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "job_agent.discover_cli", "--settings", str(args.settings),
               "--airtable-history", "--output", str(args.output_dir / f"jobs_{stamp}.json"),
               "--coverage", str(args.output_dir / f"coverage_{stamp}.json"),
               "--history-output", str(args.output_dir / f"history_{stamp}.json"),
               "--triage", str(args.output_dir / f"triage_{stamp}.json")]
    run = subprocess.run(command, capture_output=True, text=True, check=False)
    report = {"timestamp_utc": stamp, "status": "ok" if run.returncode == 0 else "failed",
              "exit_code": run.returncode, "stdout": run.stdout[-2000:], "error": run.stderr[-2000:]}
    (args.output_dir / f"run_{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if run.returncode:
        print(f"Daily discovery failed; see run_{stamp}.json", file=sys.stderr)
        raise SystemExit(run.returncode)
    coverage = json.loads((args.output_dir / f"coverage_{stamp}.json").read_text(encoding="utf-8"))
    if any(source["status"] != "ok" for source in coverage["sources"]):
        report["status"] = "partial_source_failure"
        (args.output_dir / f"run_{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise SystemExit("One or more job sources failed; inspect coverage before using results")
    print(f"Daily discovery and Airtable history check completed: {stamp}")


if __name__ == "__main__":
    main()
