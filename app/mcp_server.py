# app/trial_mcp_server.py
"""
MCP server wrapping the ClinicalTrials.gov API v2.

Exposes tools to search clinical trials by condition and retrieve trial details by NCT ID.
"""
# Import Libraries:
import asyncio
import json
import logging
import sys
import time
import urllib.parse
from typing import Any, Dict, Optional
from mcp.server.fastmcp import FastMCP

# Configure logging to write to stderr so we don't corrupt the stdio transport channel:
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("clinical_trials_mcp")

# Initialize FastMCP Server:
mcp = FastMCP("ClinicalTrials")

BASE_URL = "https://clinicaltrials.gov/api/v2"

# Default fields configurations:
DEFAULT_SEARCH_FIELDS = "NCTId,BriefTitle,OverallStatus,Phase,ConditionsModule"
DEFAULT_DETAILS_FIELDS = (
    "NCTId,BriefTitle,OverallStatus,Phase,BriefSummary,"
    "ConditionsModule,ArmsInterventionsModule,EligibilityModule"
)

# Async Rate Limiter:
class AsyncRateLimiter:
    """Limits requests to a specific QPS to respect API terms of use."""
    def __init__(self, qps: float = 1.0):
        self.interval = 1.0 / qps
        self.last_call = 0.0
        self.lock = asyncio.Lock()

    async def wait(self):
        """Asynchronously waits if the elapsed time since the last call is less than the interval."""
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.interval:
                await asyncio.sleep(self.interval - elapsed)
            self.last_call = time.time()


# 1 QPS is a safe and polite default rate limit:
rate_limiter = AsyncRateLimiter(qps=1.0)

# Curl HTTP Status Error:
class CurlHTTPStatusError(Exception):
    """Exception raised when a curl HTTP request returns an error status code."""
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text
        super().__init__(f"HTTP error {status_code}")

async def _fetch_from_api(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Helper function to perform GET requests to the ClinicalTrials.gov API using system curl.
    Uses curl to bypass TLS fingerprinting blocks that reject standard Python HTTP clients.
    Args:
        url: The request URL.
        params: Query parameters.
    Returns:
        JSON response parsed into a dictionary.
    Raises:
        CurlHTTPStatusError: If the HTTP request returned an unsuccessful status code.
        RuntimeError: If the curl process failed to execute.
    """
    await rate_limiter.wait()

    # Construct the full URL with query parameters:
    if params:
        # Filter out None values
        params_clean = {k: str(v) for k, v in params.items() if v is not None}
        query_string = urllib.parse.urlencode(params_clean)
        full_url = f"{url}?{query_string}"
    else:
        full_url = url

    logger.info("Fetching URL via curl: %s", full_url)

    # Use curl to request the URL, appending the HTTP status code at the end:
    cmd = [
        "curl",
        "-s",
        "-L",
        "--max-time", "30",
        "-w", "\nHTTP_STATUS_CODE:%{http_code}",
        full_url
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        err_msg = stderr.decode('utf-8', errors='ignore')
        logger.error("curl command failed with code %d: %s", process.returncode, err_msg)
        raise RuntimeError(f"curl failed with exit code {process.returncode}: {err_msg}")

    stdout_str = stdout.decode('utf-8', errors='ignore')
    
    # Parse status code and body:
    body_text, _, status_code_str = stdout_str.rpartition("\nHTTP_STATUS_CODE:")
    if _:
        try:
            status_code = int(status_code_str.strip())
        except ValueError:
            status_code = 200
            body_text = stdout_str
    else:
        status_code = 200
        body_text = stdout_str

    if status_code < 200 or status_code >= 300:
        raise CurlHTTPStatusError(status_code, body_text)

    # Parse JSON response:
    try:
        return json.loads(body_text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse JSON from curl response: %s", body_text[:200])
        raise ValueError(f"Invalid JSON response: {str(e)}")

# Search Trials by Condition:
@mcp.tool()
async def search_trials_by_condition(
    condition: str,
    status: Optional[str] = None,
    limit: int = 10,
    fields: Optional[str] = None,
    page_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Search clinical trials by condition (disease) and optionally by overall status.
    Args:
        condition: The disease or condition to search for (e.g., "cystic fibrosis").
        status: Filter by recruitment status. Comma-separated.
                Values: RECRUITING, NOT_YET_RECRUITING, ACTIVE_NOT_RECRUITING,
                ENROLLING_BY_INVITATION, COMPLETED, SUSPENDED, TERMINATED, WITHDRAWN.
        limit: Maximum number of trials to return (1-1000, default is 10).
        fields: Comma-separated list of JSON fields or aliases to return.
                Defaults to: "NCTId,BriefTitle,OverallStatus,Phase,ConditionsModule".
        page_token: Token for fetching the next page of results (nextPageToken).
    """
    if not condition:
        raise ValueError("The 'condition' parameter cannot be empty.")

    url = f"{BASE_URL}/studies"

    # Build query parameters
    params: Dict[str, Any] = {
        "query.cond": condition,
        "pageSize": str(limit),
        "countTotal": "true",
    }

    if status:
        params["filter.overallStatus"] = status

    params["fields"] = fields if fields else DEFAULT_SEARCH_FIELDS

    if page_token:
        params["pageToken"] = page_token

    try:
        data = await _fetch_from_api(url, params)
        return data
    except CurlHTTPStatusError as e:
        logger.error("HTTP error during search: %s", e)
        return {
            "error": f"HTTP error {e.status_code} occurred while querying ClinicalTrials.gov API.",
            "detail": e.text,
        }
    except Exception as e:
        logger.error("Unexpected error during search: %s", e)
        return {"error": f"An error occurred: {str(e)}"}

# Get Trial details:
@mcp.tool()
async def get_trial_details(
    nct_id: str,
    fields: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve details of a specific clinical trial by its unique NCT ID.
    Args:
        nct_id: The unique NCT ID of the trial (e.g., "NCT04886804").
        fields: Comma-separated list of fields or aliases to return.
                Defaults to: "NCTId,BriefTitle,OverallStatus,Phase,BriefSummary,
                ConditionsModule,ArmsInterventionsModule,EligibilityModule".
    """
    if not nct_id:
        raise ValueError("The 'nct_id' parameter cannot be empty.")

    # Standardize NCT ID format (ensure trimmed, etc.)
    nct_id_clean = nct_id.strip()

    url = f"{BASE_URL}/studies/{nct_id_clean}"

    params: Dict[str, Any] = {
        "fields": fields if fields else DEFAULT_DETAILS_FIELDS
    }

    try:
        data = await _fetch_from_api(url, params)
        return data
    except CurlHTTPStatusError as e:
        logger.error("HTTP error retrieving trial %s: %s", nct_id, e)
        if e.status_code == 404:
            return {"error": f"Trial with NCT ID {nct_id} was not found."}
        return {
            "error": f"HTTP error {e.status_code} occurred while fetching trial {nct_id}.",
            "detail": e.text,
        }
    except Exception as e:
        logger.error("Unexpected error retrieving trial %s: %s", nct_id, e)
        return {"error": f"An error occurred: {str(e)}"}

# Run the MCP server:
if __name__ == "__main__":
    mcp.run(transport="stdio")
