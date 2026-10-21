"""Create a local preparation checklist from an observed form; never fills or submits."""
import argparse
import json
from pathlib import Path

from job_agent.form_preferences import preference_plan
from job_agent.run_cli import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--preferences", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        plan = preference_plan(json.loads(args.inspection.read_text(encoding="utf-8")),
                               json.loads(args.preferences.read_text(encoding="utf-8")))
        atomic_json(args.output, plan)
        print(json.dumps({"suggestions": len(plan["answers"]),
                          "unresolved_required": len(plan["unresolved_required"]), "can_submit": False}))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, "Teamtailor preparation stopped: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
