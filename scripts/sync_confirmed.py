"""Run only after the submission agent stored a real confirmation receipt."""
import argparse
import json
from pathlib import Path

from job_agent.airtable_sync import AirtableClient
from job_agent.application import ApplicationLedger
from job_agent.models import Job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, default=Path('data/applications.sqlite'))
    args = parser.parse_args()
    jobs = [Job(**item) for item in json.loads(args.jobs.read_text(encoding='utf-8'))['jobs']]
    count = AirtableClient().sync_confirmed(ApplicationLedger(args.ledger), jobs)
    print(f'Airtable records synchronized after confirmed submission: {count}')


if __name__ == '__main__':
    main()
