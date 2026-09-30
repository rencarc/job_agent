import json
import sys
import urllib.parse
from pathlib import Path


def system_for(url: str) -> str:
    host = urllib.parse.urlparse(url or "").netloc.lower()
    if "successfactors" in host:
        return "SuccessFactors"
    if "talentech" in host:
        return "Talentech"
    if "ponty" in host:
        return "Ponty"
    if "wipro.com" in host:
        return "Wipro careers"
    if "arbetsformedlingen.se" in host:
        return "Platsbanken/company instructions"
    if not host:
        return "unknown"
    return host


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "output/jobs_today_24h.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    jobs = data["jobs"]
    print(f"count {len(jobs)}")
    counts = {}
    for index, job in enumerate(jobs, 1):
        apply_url = job.get("apply_url") or ""
        system = system_for(apply_url)
        counts[system] = counts.get(system, 0) + 1
        print(f"\n{index}. {job.get('company')} — {job.get('title')}")
        print(f"   location: {job.get('location')}")
        print(f"   published: {job.get('published_at')}")
        print(f"   system: {system}")
        print(f"   apply: {apply_url}")
    print("\nSystems:")
    for system, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"   {system}: {count}")


if __name__ == "__main__":
    main()
