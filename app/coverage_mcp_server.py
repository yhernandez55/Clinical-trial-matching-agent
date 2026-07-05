# app/coverage_mcp_server.py
"""
MCP server wrapping local insurance coverage tools.
Reads from data/sample_insurance_plans.json — no external API calls.
"""
# Import libraries:
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP

# Configure logging:
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("coverage_mcp_server")

mcp = FastMCP("CoverageMCP")

# Path to synthetic plan data — resolved relative to this file
_PLANS_PATH = Path(__file__).parent.parent / "data" / "sample_insurance_plans.json"

# Load plans:
def _load_plans() -> Dict[str, Any]:
    """Load all synthetic insurance plans from the local JSON file."""
    if not _PLANS_PATH.exists():
        raise FileNotFoundError(f"Insurance plans file not found: {_PLANS_PATH}")
    with open(_PLANS_PATH, "r") as f:
        return json.load(f)

# Define the MCP tools:
@mcp.tool()
async def load_plan(plan_name: str) -> Dict[str, Any]:
    """Load a specific insurance plan by name.
    Args:
        plan_name: Name of the insurance plan (e.g., 'BasicCare', 'PlusCare')
    Returns:
        Dict containing plan details and covered procedures,
        or an error message if the plan is not found.
    """
    try:
        plans = _load_plans()
        plan = plans.get(plan_name)
        if not plan:
            available = list(plans.keys())
            return {
                "error": f"Plan '{plan_name}' not found.",
                "available_plans": available,
            }
        logger.info("Loaded plan: %s", plan_name)
        return {"plan_name": plan_name, "details": plan}
    except FileNotFoundError as e:
        logger.error("Plans file missing: %s", e)
        return {"error": str(e)}
    except Exception as e:
        logger.error("Unexpected error loading plan: %s", e)
        return {"error": f"Failed to load plan: {str(e)}"}

# Check coverage:
@mcp.tool()
async def check_coverage(
    plan_name: str,
    procedure: str,
) -> Dict[str, Any]:
    """Check whether a specific procedure is covered under a given plan.
    Args:
        plan_name: Name of the insurance plan to check against.
        procedure: The procedure or service type to check
                   (e.g., 'lab_visit', 'imaging', 'specialist_visit').
    Returns:
        Dict with coverage status, coverage percentage,
        prior authorization requirements, and any relevant caveats.
    """
    try:
        plans = _load_plans()
        plan = plans.get(plan_name)
        if not plan:
            return {"error": f"Plan '{plan_name}' not found."}

        covered_procedures = plan.get("covered_procedures", {})
        coverage = covered_procedures.get(procedure)

        if not coverage:
            return {
                "plan_name": plan_name,
                "procedure": procedure,
                "covered": False,
                "reason": "Procedure not listed in plan's covered services.",
            }

        logger.info("Coverage check: plan=%s procedure=%s", plan_name, procedure)
        return {
            "plan_name": plan_name,
            "procedure": procedure,
            "covered": coverage.get("covered", False),
            "coverage_percentage": coverage.get("coverage_percentage"),
            "prior_auth_required": coverage.get("prior_auth_required", False),
            "caveats": coverage.get("caveats", "None"),
        }
    except Exception as e:
        logger.error("Unexpected error checking coverage: %s", e)
        return {"error": f"Coverage check failed: {str(e)}"}

# Run the server:
if __name__ == "__main__":
    mcp.run(transport="stdio")

