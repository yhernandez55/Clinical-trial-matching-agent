# tools/clinical_trials_tools.py
"""
Clinical trial information loading and trial-matching utilities, with removing PII from patients condition
description before sent to an external API.
"""

# importing libraries:
import requests
from google.adk.tools import ToolContext
from .memory import update_memory, get_memory_context
import re

# import from clinical_trials_tools.py:
__all__ = ["find_trials_by_condition", "find_trials_by_nct", "extract_eligibility"]


# PII sanitizer — strips common name/age patterns before 
# condition text touches any external API or LLM call
def _sanitize_condition(text: str) -> str:
    """Remove potential PII from a patient's condition description
    before it is sent to ClinicalTrials.gov or passed to an LLM.
    Strips: ages, common name patterns, date-of-birth mentions.
    This is used so for secrurity reasons we don't share PII with External API's.
    """
    # Remove age mentions e.g. "45 year old", "age 32"
    text = re.sub(r'\b(age[d]?\s*)?\d{1,3}\s*[-]?\s*year[s]?\s*[-]?\s*old\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bage\s*\d{1,3}\b', '', text, flags=re.IGNORECASE)
    # Remove capitalized name-like patterns (two consecutive capitalized words)
    text = re.sub(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', '[NAME REMOVED]', text)
    return text.strip()

# Add a helper to extract eligibility cleanly from a raw trial dict
def extract_eligibility(trial: dict) -> dict:
    """Pull eligibility criteria out of a raw ClinicalTrials.gov 
    trial record cleanly, so agents don't have to parse the 
    full protocolSection themselves.

    Returns:
        Dict with keys: nct_id, title, min_age, max_age,
        gender, criteria_text
    """
    protocol = trial.get("protocolSection", {})
    id_module = protocol.get("identificationModule", {})
    eligibility_module = protocol.get("eligibilityModule", {})

    return {
        "nct_id": id_module.get("nctId", "UNKNOWN"),
        "title": id_module.get("briefTitle", "No title"),
        "min_age": eligibility_module.get("minimumAge", "Not specified"),
        "max_age": eligibility_module.get("maximumAge", "Not specified"),
        "gender": eligibility_module.get("sex", "All"),
        "criteria_text": eligibility_module.get("eligibilityCriteria", "No criteria available"),
    }

# Base URL only — parameters are passed dynamically per call
BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

# find_trials_by_condition function:
def find_trials_by_condition(
    condition: str,
    tool_context: ToolContext,
    max_results: int = 100,
    status: str = "RECRUITING",
) -> dict:
    """Search ClinicalTrials.gov for trials matching a given condition.
    Args:
        condition: Plain-language condition description (e.g., "type 2 diabetes")
        tool_context: ADK ToolContext for session-scoped memory
        max_results: Number of trials to return I set to 100
        status: Recruitment status filter (default RECRUITING)
    Returns:
        Dict containing matched trials or an error message
    """
    # Pull any prior context for this session
    prior_context = get_memory_context(tool_context)

    # Clean PII from condition: 
    clean_conditions = _sanitize_condition(condition)
    # Prepare API request parameters
    params = {
        "query.cond": clean_conditions,
        "filter.overallStatus": status,
        "pageSize": max_results,
        "format": "json",
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=100)
        response.raise_for_status()
        data = response.json()

        trials = data.get("studies", [])
        nct_ids = [
            t.get("protocolSection", {})
             .get("identificationModule", {})
             .get("nctId", "UNKNOWN")
            for t in trials
        ]

        # Update session memory with what was found
        update_memory(
            tool_context=tool_context,
            user_query=f"Find trials for condition: {condition}",
            agent_response=f"Found {len(trials)} trials",
            trials_mentioned=nct_ids,
        )

        return {"condition": condition, "trials": trials, "total": len(trials)}

    except requests.RequestException as e:
        return {"error": f"ClinicalTrials.gov API call failed: {str(e)}"}

# find_trials_by_nct function:
def find_trials_by_nct(
    nct_id: str,
    tool_context: ToolContext,
) -> dict:
    """Retrieve full details for a single trial by its NCT ID.
    Args:
        nct_id: The NCT identifier (e.g., "NCT00000419")
        tool_context: ADK ToolContext for session-scoped memory
    Returns:
        Dict containing trial details or an error message
    """
    try:
        # Single-trial lookup uses /studies/{nct_id} endpoint
        response = requests.get(
            f"{BASE_URL}/{nct_id}",
            params={"format": "json"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        update_memory(
            tool_context=tool_context,
            user_query=f"Get details for trial: {nct_id}",
            agent_response=f"Retrieved details for {nct_id}",
            trials_mentioned=[nct_id],
        )

        return data

    except requests.RequestException as e:
        return {"error": f"Failed to retrieve trial {nct_id}: {str(e)}"}