# app/agent.py
"""
Root coordinator agent for the clinical trial matching system.
Orchestrates the trial-matching agent and the coverage-checking agent,
and synthesizes their results into a patient-friendly summary.
"""
# Importing libraries:
import os
import asyncio
import contextlib
import atexit
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool
from .trial_matching_agent import create_trial_matching_agent
from .coverage_checking_agent import create_coverage_checking_agent
from tools.memory import update_memory, get_memory_context

# Create the root agent:
async def create_root_agent():
    """Create the root coordinator agent and manage child resources.
    Returns:
        A tuple of (LlmAgent, AsyncExitStack).
    """
    combined_exit_stack = contextlib.AsyncExitStack()

    try:
        trial_agent, trial_stack = await create_trial_matching_agent()
        await combined_exit_stack.enter_async_context(trial_stack)

        coverage_agent, coverage_stack = await create_coverage_checking_agent()
        await combined_exit_stack.enter_async_context(coverage_stack)

    except Exception as e:
        await combined_exit_stack.aclose()
        raise e

    instruction = """
    You are the root coordinator for a clinical trial matching system.
    Your goal is to help patients find relevant clinical trials and check if
    their health insurance plan covers the procedures involved, then provide a
    single, cohesive, plain-language recommendation.

    Workflow:
    1. First, delegate to the trial_matching_agent using the patient's
       plain-language condition description to find matching trials.
    2. Then, delegate to the coverage_checking_agent using the relevant
       procedures/tests required by the matched trials and the patient's
       health insurance plan name to check plan coverage.
    3. Synthesize both sets of results into a single plain-language response.

    Important Rules:
    - Never repeat, log, or persist personally identifying patient information (PII).
    - Always output a clear, friendly summary of what trials are relevant,
      what is covered, and any prior authorization or out-of-pocket caveats.
    - Clearly state that this output is a starting point for the patient to
      discuss with their provider, and NOT medical or financial advice.
    """

    root_agent = LlmAgent(
        name="root_coordinator",
        model="gemini-2.0-flash",
        instruction=instruction,
        tools=[
            AgentTool(trial_agent),
            AgentTool(coverage_agent),
        ],
    )

    return root_agent, combined_exit_stack

# Module-level root_agent for ADK discovery
root_agent, _combined_stack = asyncio.run(create_root_agent())

# Register exit stack cleanup on process termination
def _cleanup():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_running():
        loop.create_task(_combined_stack.aclose())
    else:
        loop.run_until_complete(_combined_stack.aclose())

atexit.register(_cleanup)
