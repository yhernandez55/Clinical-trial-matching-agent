# app/trial_matching_agent.py
"""
Trial-matching agent that searches ClinicalTrials.gov for relevant
clinical trials based on a patient's plain-language condition description.
Tool calls are routed through the ClinicalTrials MCP server via stdio transport.
"""
# Importing libraries:
import os
import sys
import contextlib
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters
from tools.memory import update_memory, get_memory_context

# Path to the MCP server script, resolved relative to this file:
_MCP_SERVER_PATH = str(Path(__file__).parent / "trial_mcp_server.py")

# Create the trial-matching agent:
async def create_trial_matching_agent():
    """Create and return the trial-matching LlmAgent and its exit stack.
    Connects to the local ClinicalTrials MCP server via stdio transport.
    The caller is responsible for closing the exit stack when done to
    cleanly shut down the MCP subprocess.
    Returns:
        A tuple of (LlmAgent, AsyncExitStack).
        Call ``await exit_stack.aclose()`` when the agent is no longer needed.
    """
    exit_stack = contextlib.AsyncExitStack()

    # Connect to the local MCP server subprocess via stdio:
    toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[_MCP_SERVER_PATH],
            )
        )
    )

    # Register cleanup so the MCP subprocess is terminated on exit:
    exit_stack.push_async_callback(toolset.close)

    # System prompt for the trial-matching agent:
    instruction = """
    You are a clinical trial matching assistant.
    Given a patient's plain-language description of their medical condition,
    use the search_trials_by_condition tool to find relevant recruiting trials.
    Use get_trial_details to retrieve full eligibility criteria for the most
    promising matches.

    Guidelines:
    - Always explain trial results in plain, accessible language.
    - Summarise eligibility criteria clearly so a patient can self-assess.
    - Never repeat, store, or infer personally identifying patient information.
    - If no recruiting trials are found, say so clearly and suggest the patient
      speak with their doctor about other options.
    """

    # Build the agent with gemini-2.5-flash and the MCP toolset:
    agent = LlmAgent(
        name="trial_matching_agent",
        model="gemini-2.5-flash",
        instruction=instruction,
        tools=[toolset],
    )

    return agent, exit_stack