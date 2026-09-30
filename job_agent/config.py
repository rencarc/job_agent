import os

SHADOW_MODE = True
AUTO_REJECT = False
AUTO_SUBMIT = False

STRONG_THRESHOLD = 80
MAYBE_THRESHOLD = 65
MIN_AUTO_DECISION_CONFIDENCE = 0.80

# Airtable tracker configuration. Keep real IDs in environment variables or a
# local ignored settings file, never in the public repository.
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_ID = os.environ.get("AIRTABLE_TABLE_ID", "")
AIRTABLE_FIELDS = {
    "application": os.environ.get("AIRTABLE_FIELD_APPLICATION", "application"),
    "company": os.environ.get("AIRTABLE_FIELD_COMPANY", "company"),
    "role": os.environ.get("AIRTABLE_FIELD_ROLE", "role"),
    "job_link": os.environ.get("AIRTABLE_FIELD_JOB_LINK", "job_link"),
    "location": os.environ.get("AIRTABLE_FIELD_LOCATION", "location"),
    "status": os.environ.get("AIRTABLE_FIELD_STATUS", "status"),
    "match_score": os.environ.get("AIRTABLE_FIELD_MATCH_SCORE", "match_score"),
    "priority": os.environ.get("AIRTABLE_FIELD_PRIORITY", "priority"),
    "key_requirements": os.environ.get("AIRTABLE_FIELD_KEY_REQUIREMENTS", "key_requirements"),
    "missing_skills": os.environ.get("AIRTABLE_FIELD_MISSING_SKILLS", "missing_skills"),
    "language_risk": os.environ.get("AIRTABLE_FIELD_LANGUAGE_RISK", "language_risk"),
    "permit_risk": os.environ.get("AIRTABLE_FIELD_PERMIT_RISK", "permit_risk"),
    "jd_text": os.environ.get("AIRTABLE_FIELD_JD_TEXT", "jd_text"),
    "result": os.environ.get("AIRTABLE_FIELD_RESULT", "result"),
    "human_decision": os.environ.get("AIRTABLE_FIELD_HUMAN_DECISION", "human_decision"),
    "human_reject_reason": os.environ.get("AIRTABLE_FIELD_HUMAN_REJECT_REASON", "human_reject_reason"),
    "human_override_reason": os.environ.get("AIRTABLE_FIELD_HUMAN_OVERRIDE_REASON", "human_override_reason"),
    "label_date": os.environ.get("AIRTABLE_FIELD_LABEL_DATE", "label_date"),
    "jd_snapshot_hash": os.environ.get("AIRTABLE_FIELD_JD_SNAPSHOT_HASH", "jd_snapshot_hash"),
    "submitted_date": os.environ.get("AIRTABLE_FIELD_SUBMITTED_DATE", "submitted_date"),
    "application_notes": os.environ.get("AIRTABLE_FIELD_APPLICATION_NOTES", "application_notes"),
}
