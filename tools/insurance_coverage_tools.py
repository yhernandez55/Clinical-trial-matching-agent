# tools/insurance_coverage_tools.py
"""
Insurance plan loading and coverage-checking utilities.

These tools integrate with the ADK session system (via ToolContext) and are
designed to be called by coverage_checking_agent once it is built.  Patient
data is treated as sensitive: PII is stripped before any coverage logic runs,
and nothing is written to logs or persisted beyond the current session state.
"""

# Importing libraries:
import json
import pathlib
import re
from typing import Any
from google.adk.tools import ToolContext
from .memory import update_memory

# __all__ is a list of strings that defines the public API of the module:
__all__ = ["load_insurance_plan", "check_coverage"]

# Path is relative to this file so the module works regardless of cwd.
_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
_PLANS_FILE = _DATA_DIR / "sample_insurance_plans.json"

# Session-state key where the currently-loaded plan is cached.
_PLAN_STATE_KEY = "loaded_insurance_plan"

# Procedure types the coverage-checker knows how to match.
# Keys align with the keys inside each plan's covered_procedures dict.
_KNOWN_PROCEDURE_TYPES = {
    "lab_visit",
    "imaging_mri",
    "imaging_ct",
    "imaging_pet",
    "specialist_visit",
    "investigational_treatment",
    "infusion_therapy",
    "genetic_testing",
    "clinical_trial_routine_care",
}

# PII sanitization
def _sanitize_procedure_data(data: dict) -> dict:
    """Return a shallow-sanitized copy of ``data`` with PII removed from
    any string values.

    Mirrors ``_sanitize_condition`` in clinical_trials_tools.py:
    - Strips age patterns ("45-year-old", "age 32")
    - Replaces adjacent-capitalized-word name patterns with [NAME REMOVED]
    - Does NOT modify list or nested-dict values beyond the top level
      (trial eligibility text is already sanitized upstream).
    """
    sanitized: dict = {}
    for key, value in data.items():
        if isinstance(value, str):
            value = re.sub(
                r'\b(age[d]?\s*)?\d{1,3}\s*[-]?\s*year[s]?\s*[-]?\s*old\b',
                '', value, flags=re.IGNORECASE,
            )
            value = re.sub(r'\bage\s*\d{1,3}\b', '', value, flags=re.IGNORECASE)
            value = re.sub(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', '[NAME REMOVED]', value)
            sanitized[key] = value.strip()
        else:
            sanitized[key] = value
    return sanitized

# Internal helpers
def _load_plans_file() -> list:
    """Read and return the list of plans from the JSON data file.
    Raises:
        FileNotFoundError: If sample_insurance_plans.json is missing.
        ValueError: If the file cannot be parsed as valid JSON.
    """
    if not _PLANS_FILE.exists():
        raise FileNotFoundError(
            f"Insurance plans data file not found at: {_PLANS_FILE}. "
            "Ensure data/sample_insurance_plans.json exists in the project root."
        )
    try:
        with _PLANS_FILE.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse insurance plans file: {exc}") from exc

    plans = payload.get("plans")
    if not isinstance(plans, list):
        raise ValueError("Insurance plans file must contain a top-level 'plans' list.")
    return plans

# Heuristic: infer procedure type from text fields:
def _infer_procedure_type(procedure_or_trial: dict) -> str | None:
    """Best-effort mapping from trial/procedure fields to a known procedure key.
    Checks for an explicit ``procedure_type`` field first, then falls back to
    keyword matching against the ``title`` or ``criteria_text`` fields that
    ``extract_eligibility()`` produces.
    """
    # Caller can supply an explicit type — honour it if valid.
    explicit = procedure_or_trial.get("procedure_type", "")
    if explicit in _KNOWN_PROCEDURE_TYPES:
        return explicit

    # Keyword heuristics over text fields
    text_blob = " ".join(
        str(procedure_or_trial.get(f, ""))
        for f in ("title", "criteria_text", "description", "procedure_type")
    ).lower()

    if any(kw in text_blob for kw in ("mri", "magnetic resonance")):
        return "imaging_mri"
    if any(kw in text_blob for kw in ("ct scan", "computed tomography")):
        return "imaging_ct"
    if any(kw in text_blob for kw in ("pet scan", "positron emission")):
        return "imaging_pet"
    if any(kw in text_blob for kw in ("lab", "blood draw", "biopsy", "specimen")):
        return "lab_visit"
    if any(kw in text_blob for kw in ("infusion", "iv therapy", "intravenous")):
        return "infusion_therapy"
    if any(kw in text_blob for kw in ("genetic", "genomic", "sequencing", "biomarker")):
        return "genetic_testing"
    if any(kw in text_blob for kw in ("specialist", "oncologist", "neurologist", "cardiologist")):
        return "specialist_visit"
    if any(kw in text_blob for kw in ("investigational", "experimental", "phase i", "phase ii", "phase iii")):
        return "investigational_treatment"
    if any(kw in text_blob for kw in ("clinical trial", "routine care", "standard of care")):
        return "clinical_trial_routine_care"

    return None

# Public API
# Loading insurance plans:
def load_insurance_plan(plan_name: str, tool_context: ToolContext) -> dict:
    """Load a named insurance plan and cache it in the session state.
    The loaded plan is stored in ``tool_context.state`` under the key
    ``"loaded_insurance_plan"`` so that subsequent calls to
    ``check_coverage()`` can access it without re-reading the file.
    Args:
        plan_name: Case-insensitive name of the plan to load
            (e.g., "BlueCare Standard PPO").
        tool_context: ADK ToolContext providing session-scoped state.
    Returns:
        The matching plan dict on success, or a dict with an "error" key.
    """
    try:
        plans = _load_plans_file()
    except (FileNotFoundError, ValueError) as exc:
        return {"error": str(exc)}

    # Case-insensitive name match
    matched = next(
        (p for p in plans if p.get("plan_name", "").lower() == plan_name.lower()),
        None,
    )
    if matched is None:
        available = [p.get("plan_name", "?") for p in plans]
        return {
            "error": f"Plan '{plan_name}' not found.",
            "available_plans": available,
        }

    # Cache in session state so check_coverage() can retrieve it
    tool_context.state[_PLAN_STATE_KEY] = matched

    update_memory(
        tool_context=tool_context,
        user_query=f"Load insurance plan: {plan_name}",
        agent_response=(
            f"Loaded plan '{matched['plan_name']}' "
            f"(type: {matched.get('plan_type', 'unknown')})"
        ),
        trials_mentioned=[],
    )

    # Return a copy — callers should not mutate state directly
    return dict(matched)

# Checking insurance coverage: 
def check_coverage(procedure_or_trial: dict, tool_context: ToolContext) -> dict:
    """Evaluate what a loaded plan covers for a given procedure or trial.
    Call ``load_insurance_plan()`` before this function to set the active plan
    in the session.  The function reads it back from ``tool_context.state``
    automatically.
    ``procedure_or_trial`` can be:
    - The output of ``extract_eligibility()`` from clinical_trials_tools.py
    - A plain dict with at least a ``"procedure_type"`` key (one of the keys
      in _KNOWN_PROCEDURE_TYPES)
    A PII sanitization pass runs on all string fields before any logic executes.
    Args:
        procedure_or_trial: Dict describing the trial or procedure to evaluate.
        tool_context: ADK ToolContext providing session-scoped state.
    Returns:
        A dict with keys:
        - "procedure_type"       -- resolved type string or "unknown"
        - "covered"              -- bool or None if plan not loaded
        - "coverage_pct"         -- int percentage or 0
        - "prior_auth_required"  -- bool
        - "notes"                -- human-readable caveat string
        - "plan_name"            -- name of the plan evaluated against
        - "caveats"              -- list of additional warnings
        - "error"                -- only present on hard failures
    """
    caveats = []

    # Input validation:
    if not isinstance(procedure_or_trial, dict):
        return {"error": "procedure_or_trial must be a dict."}
    if not procedure_or_trial:
        return {"error": "procedure_or_trial dict is empty."}

    # PII sanitization (before any coverage logic):
    safe_data = _sanitize_procedure_data(procedure_or_trial)

    # Retrieve cached plan:
    plan = tool_context.state.get(_PLAN_STATE_KEY)
    if plan is None:
        caveats.append(
            "No insurance plan loaded for this session. "
            "Call load_insurance_plan() first."
        )
        return {
            "procedure_type": "unknown",
            "covered": None,
            "coverage_pct": 0,
            "prior_auth_required": False,
            "notes": "",
            "plan_name": "none",
            "caveats": caveats,
        }

    # Infer procedure type
    procedure_type = _infer_procedure_type(safe_data)
    if procedure_type is None:
        caveats.append(
            "Could not determine procedure type from the supplied data. "
            f"Provide a 'procedure_type' key with one of: {sorted(_KNOWN_PROCEDURE_TYPES)}"
        )
        procedure_type = "unknown"

    # Look up coverage:
    covered_procedures = plan.get("covered_procedures", {})
    coverage_entry = covered_procedures.get(procedure_type)

    if coverage_entry is None:
        caveats.append(
            f"Procedure type '{procedure_type}' is not listed in plan "
            f"'{plan.get('plan_name')}'. It may default to not covered."
        )
        result = {
            "procedure_type": procedure_type,
            "covered": False,
            "coverage_pct": 0,
            "prior_auth_required": False,
            "notes": "Procedure type not found in plan schedule of benefits.",
            "plan_name": plan.get("plan_name", "unknown"),
            "caveats": caveats,
        }
    else:
        result = {
            "procedure_type": procedure_type,
            "covered": coverage_entry.get("covered", False),
            "coverage_pct": coverage_entry.get("coverage_pct", 0),
            "prior_auth_required": coverage_entry.get("prior_auth_required", False),
            "notes": coverage_entry.get("notes", ""),
            "plan_name": plan.get("plan_name", "unknown"),
            "caveats": caveats,
        }

    # Persist to session memory:
    nct_id = safe_data.get("nct_id", "N/A")
    update_memory(
        tool_context=tool_context,
        user_query=f"Check coverage for procedure: {procedure_type} (trial: {nct_id})",
        agent_response=(
            f"Covered: {result['covered']} at {result['coverage_pct']}% "
            f"under {result['plan_name']}. Prior auth: {result['prior_auth_required']}."
        ),
        trials_mentioned=[nct_id] if nct_id != "N/A" else [],
    )

    return result
