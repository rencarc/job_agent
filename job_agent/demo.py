from dataclasses import asdict
from pprint import pprint

from .models import Job
from .scoring import score_job


job = Job(
    external_id="demo-1",
    company="Example",
    title="Junior Power Platform and Copilot Studio Developer",
    location="Stockholm",
    description="Build Copilot Studio agents, Power Automate workflows, Dataverse integrations and Azure AI solutions. English required; Swedish is a plus.",
    apply_url="https://example.test/jobs/demo-1",
)

pprint(asdict(score_job(job)))

