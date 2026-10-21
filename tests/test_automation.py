import tempfile
import json
import hashlib
import unittest
from dataclasses import replace
from pathlib import Path

from job_agent.automation import Limits, load_profile, run_pipeline, validate_profile
from job_agent.config import AIRTABLE_FIELDS
from job_agent.models import Job
from job_agent.store import JobStore


def profile():
    return {"confirmed_by_user": True, "country_code": "SE", "target_titles": ["AI Engineer"],
            "languages": ["en"], "min_skill_matches": 2,
            "facts": {"project": "Built Python API integration"},
            "skills": {"Python": ["project"], "API": ["project"]}}


def job(index=1):
    return Job(str(index), "Acme", "AI Engineer", "Stockholm", "Build Python API integrations.",
               source="jobtech", source_url=f"https://example.test/{index}", location_status="sweden")


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "jobs.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def test_restart_reuses_evaluation_and_preserves_versions(self):
        with JobStore(self.path) as store:
            first = run_pipeline(store, [job()], profile(), history_records=[])
            self.assertEqual(first["counts"], {"prepare": 1})
            self.assertFalse(first["tasks"][0]["can_submit"])
        with JobStore(self.path) as store:
            second = run_pipeline(store, [replace(job(), discovered_at="tomorrow")], profile(), history_records=[])
            self.assertEqual(second["evaluated"], 0)
            self.assertEqual(second["cached"], 1)
            self.assertEqual(store.db.execute("SELECT count(*) FROM job_versions").fetchone()[0], 1)
            third = run_pipeline(store, [replace(job(), description="Python API updated requirements.")], profile(), history_records=[])
            self.assertEqual(third["evaluated"], 1)
            self.assertEqual(store.db.execute("SELECT count(*) FROM job_versions").fetchone()[0], 2)

    def test_profile_change_invalidates_match(self):
        with JobStore(self.path) as store:
            run_pipeline(store, [job()], profile(), history_records=[])
            updated = profile()
            updated["target_titles"] = ["Data Engineer"]
            result = run_pipeline(store, [], updated, history_records=[])
            self.assertEqual(result["evaluated"], 1)
            self.assertEqual(result["counts"], {"exception": 1})

    def test_preferred_city_changes_order_without_excluding_other_sweden(self):
        preferences = profile()
        preferences["preferred_locations"] = ["Stockholm"]
        with JobStore(self.path) as store:
            result = run_pipeline(store, [replace(job(1), location="Gothenburg"), job(2)],
                                  preferences, history_records=[])
            self.assertEqual(result["counts"], {"prepare": 2})
            self.assertEqual([task["location_priority"] for task in result["tasks"]], [0, 1])

    def test_history_is_rechecked_even_when_match_cached(self):
        with JobStore(self.path) as store:
            run_pipeline(store, [job()], profile(), history_records=[])
            records = [{"id": "rec1", "fields": {AIRTABLE_FIELDS["job_link"]: job().source_url,
                                                    AIRTABLE_FIELDS["status"]: "Applied"}}]
            result = run_pipeline(store, [], profile(), history_records=records)
            self.assertEqual(result["evaluated"], 0)
            self.assertEqual(result["counts"], {"skip": 1})

    def test_unknown_history_never_becomes_verified_empty_history(self):
        with JobStore(self.path) as store:
            result = run_pipeline(store, [job()], profile())
            self.assertEqual(result["counts"], {"exception": 1})
            self.assertEqual(run_pipeline(store, [], profile(), history_records=[])["counts"], {"prepare": 1})

    def test_draft_preview_is_isolated_and_cannot_become_actionable(self):
        draft = {**profile(), "confirmed_by_user": False}
        with JobStore(self.path) as store:
            result = run_pipeline(store, [job()], draft, preview=True)
            self.assertEqual(result["counts"], {"preview": 1})
            self.assertEqual(result["tasks"][0]["suggested_decision"], "prepare")
            self.assertEqual(result["tasks"][0]["routing_decision"], "exception")
            self.assertFalse(result["tasks"][0]["can_submit"])
            with self.assertRaises(ValueError):
                run_pipeline(store, [], profile(), history_records=[])

    def test_preview_sorts_suggested_prepare_ahead_of_high_scoring_exceptions(self):
        draft = {**profile(), "confirmed_by_user": False, "technical_seniority": "early_career"}
        with JobStore(self.path) as store:
            result = run_pipeline(store, [replace(job(1), title="Senior AI Engineer"), job(2)], draft, preview=True)
            self.assertEqual([t["suggested_decision"] for t in result["tasks"]], ["prepare", "exception"])

    def test_title_city_beats_staffing_agency_location_for_priority_only(self):
        preferences = {**profile(), "preferred_locations": ["Stockholm"]}
        with JobStore(self.path) as store:
            result = run_pipeline(store, [replace(job(1), title="AI Engineer - Gothenburg"), job(2)], preferences, history_records=[])
            self.assertEqual(result["counts"], {"prepare": 2})
            self.assertEqual([t["location_priority"] for t in result["tasks"]], [0, 1])

    def test_preview_retains_real_mismatch_reasons_and_does_not_call_models(self):
        draft = {**profile(), "confirmed_by_user": False}
        with JobStore(self.path) as store:
            result = run_pipeline(store, [replace(job(), description="Python API. Finnish required.")], draft, preview=True)
            reasons = result["tasks"][0]["reasons"]
            self.assertTrue(any("language" in reason for reason in reasons))
            self.assertIn("application history is unverified", reasons)
            with self.assertRaises(ValueError):
                run_pipeline(store, [], draft, preview=True, evaluator=lambda *a, **k: {}, evaluator_version="test")

    def test_bounded_runs_resume_backlog_without_new_discovery(self):
        jobs = [job(i) for i in range(1000)]
        limits = Limits(max_evaluations=400)
        with JobStore(self.path) as store:
            first = run_pipeline(store, jobs, profile(), history_records=[], limits=limits)
            self.assertEqual(first["evaluated"], 400)
            self.assertEqual(first["deferred"], 600)
            self.assertEqual(first["counts"]["deferred"], 600)
        with JobStore(self.path) as store:
            second = run_pipeline(store, [], profile(), history_records=[], limits=limits)
            third = run_pipeline(store, [], profile(), history_records=[], limits=limits)
            self.assertEqual(second["evaluated"], 400)
            self.assertEqual(third["evaluated"], 200)
            self.assertEqual(third["counts"], {"prepare": 1000})
            self.assertEqual(third["usage_today"], {"calls": 0, "tokens": 0})

    def test_elapsed_budget_defers_instead_of_dropping(self):
        ticks = iter([0, 10, 10])
        with JobStore(self.path) as store:
            result = run_pipeline(store, [job()], profile(), history_records=[],
                                  limits=Limits(max_seconds=1), clock=lambda: next(ticks))
            self.assertEqual(result["deferred"], 1)
            self.assertEqual(len(store.jobs()), 1)

    def test_overlapping_runs_are_rejected(self):
        with JobStore(self.path) as first, JobStore(self.path) as second:
            with first.lease("automation", seconds=60):
                with self.assertRaisesRegex(RuntimeError, "active"):
                    run_pipeline(second, [job()], profile(), history_records=[])
            self.assertEqual(run_pipeline(second, [job()], profile(), history_records=[])["evaluated"], 1)

    def test_invalid_profile_cannot_become_an_automatic_decision(self):
        bad = profile()
        bad["confirmed_by_user"] = False
        with self.assertRaises(ValueError):
            validate_profile(bad)
        bad = profile()
        bad["skills"]["Python"] = ["imaginary"]
        with self.assertRaises(ValueError):
            validate_profile(bad)
        with self.assertRaises(ValueError):
            Limits(max_evaluations=-1)

    def test_source_hash_change_invalidates_extracted_profile(self):
        source = Path(self.tmp.name) / "cv.pdf"
        source.write_bytes(b"sample CV bytes")
        value = {**profile(), "source_document": str(source),
                 "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        path = Path(self.tmp.name) / "profile.json"
        path.write_text(json.dumps(value))
        self.assertEqual(load_profile(path), value)
        source.write_bytes(b"updated CV bytes")
        with self.assertRaisesRegex(ValueError, "CV changed"):
            load_profile(path)

    def test_model_allowance_persists_across_restarts(self):
        limits = Limits(daily_model_calls=1, daily_tokens=500, tokens_per_call=500)
        calls = []
        def evaluate(job, profile, *, max_tokens):
            calls.append(max_tokens)
            return {"priority": 90, "tokens": 100}
        with JobStore(self.path) as store:
            result = run_pipeline(store, [job(1), job(2)], profile(), history_records=[], limits=limits,
                                  evaluator=evaluate, evaluator_version="fixture-1")
            self.assertEqual(result["usage_today"], {"calls": 1, "tokens": 100})
            self.assertEqual(result["deferred"], 1)
        with JobStore(self.path) as store:
            result = run_pipeline(store, [], profile(), history_records=[], limits=limits,
                                  evaluator=evaluate, evaluator_version="fixture-1")
            self.assertEqual(len(calls), 1)
            self.assertEqual(result["deferred"], 1)

    def test_failed_model_call_keeps_reservation_and_is_not_cached(self):
        def fail(*args, **kwargs):
            raise TimeoutError("unknown billing result")
        with JobStore(self.path) as store:
            result = run_pipeline(store, [job()], profile(), history_records=[],
                                  limits=Limits(daily_model_calls=1, daily_tokens=500, tokens_per_call=500),
                                  evaluator=fail, evaluator_version="fixture-1")
            self.assertEqual(result["usage_today"], {"calls": 1, "tokens": 500})
            self.assertEqual(store.db.execute("SELECT count(*) FROM evaluations").fetchone()[0], 0)
            self.assertEqual(result["counts"], {"exception": 1})

    def test_default_allowance_never_calls_optional_model(self):
        def unexpected(*args, **kwargs):
            self.fail("model invoked with zero budget")
        with JobStore(self.path) as store:
            result = run_pipeline(store, [job()], profile(), history_records=[],
                                  evaluator=unexpected, evaluator_version="fixture-1")
            self.assertEqual(result["deferred"], 1)

    def test_model_priority_cannot_override_eligibility_or_submit(self):
        with JobStore(self.path) as store:
            result = run_pipeline(store, [replace(job(), description="Python API. Finnish is required.")],
                                  profile(), history_records=[], limits=Limits(daily_model_calls=1, daily_tokens=500, tokens_per_call=500),
                                  evaluator=lambda *a, **k: {"priority": 100, "tokens": 10}, evaluator_version="fixture-1")
            self.assertEqual(result["counts"], {"exception": 1})
            self.assertFalse(result["tasks"][0]["can_submit"])

    def test_identity_aliases_and_different_requisitions(self):
        with JobStore(self.path) as store:
            a, _ = store.ingest(job())
            b, changed = store.ingest(replace(job(), source="other", external_id="alias"))
            c, _ = store.ingest(job(2))
            self.assertEqual(a, b)
            self.assertFalse(changed)
            self.assertNotEqual(a, c)
            self.assertEqual(len(store.jobs()), 2)
