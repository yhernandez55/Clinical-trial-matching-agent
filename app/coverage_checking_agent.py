# app/coverage_checking_agent.py
"""
Coverage checking agent that uses MCP to interact with the coverage checking MCP server.
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

# path to the MCP server script, resolved relative to this file:
_MCP_SERVER_PATH = str(Path(__file__).parent / "coverage_mcp_server.py")

# Create the coverage-checking agent:
async def create_coverage_checking_agent():
    """Create and return the coverage-checking agent and its exit stack.
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

    # System prompt for the coverage-checking agent:
    instruction = """
    You are a health insurance coverage expert.
    Your role is to determine whether a specific medical service, treatment, or
    item is covered by a health insurance plan. You use the coverage-checking
    MCP toolset to query the payer’s policy database.
    """

    # Build the agent with gemini-2.5-flash and the MCP toolset:
    agent = LlmAgent(
        name="coverage_checking_agent",
        model="gemini-2.0-flash",
        instruction=instruction,
        tools=[toolset],
    )

    return agent, exit_stack
        