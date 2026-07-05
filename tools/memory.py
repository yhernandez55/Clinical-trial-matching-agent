# tools/memory.py
"""
Session-scoped memory for clinical-trial matching agents.

Instead of a global list (shared across all sessions/users), conversation
history is stored inside the ADK session's state dictionary.  Each session
gets its own isolated ``conversation_history`` key, and the ADK Runner
maintains the state for us — no custom session-ID generation needed.
"""

# Importing libraries:
from datetime import datetime, timezone
from google.adk.tools import ToolContext  # matches the import in app/agent.py

# State key used to store the conversation history list inside
# the session's ``state`` dictionary.
_HISTORY_KEY = "conversation_history"

# Internal helpers:
def _get_history(tool_context: ToolContext) -> list:
    """Return the mutable history list stored in the session state.

    The first call on a fresh session initialises the list.
    """
    if _HISTORY_KEY not in tool_context.state:
        tool_context.state[_HISTORY_KEY] = []
    return tool_context.state[_HISTORY_KEY]

# Public API — called by trial_matching_agent and coverage_checking_agent:
def update_memory(
    tool_context: ToolContext,
    user_query: str,
    agent_response: str,
    trials_mentioned: list,
) -> None:
    """Append one interaction turn to this session's conversation history.
    Args:
        tool_context: The ADK ToolContext injected by the framework.
            It carries the session state, so memory is automatically
            scoped to the current user session.
        user_query: The raw question or input from the user.
        agent_response: The agent's reply or summary.
        trials_mentioned: List of NCT IDs (or trial dicts) referenced
            in this turn.
    """
    history = _get_history(tool_context)
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": user_query,
        "response": agent_response,
        "trials": trials_mentioned,
    })
    # Write the updated list back — some ADK state backends require explicit
    # re-assignment to register the mutation.
    tool_context.state[_HISTORY_KEY] = history

# Get memory context for LLM context:
def get_memory_context(tool_context: ToolContext) -> str:
    """Return a formatted summary of the last 3 turns for LLM context.
    Args:
        tool_context: The ADK ToolContext injected by the framework.
    Returns:
        A plain-text block describing recent queries and trials, or an
        empty string if there is no history yet.
    """
    history = _get_history(tool_context)
    recent = history[-3:]

    if not recent:
        return ""

    lines = ["User context from previous interactions:"]
    for turn in recent:
        lines.append(
            f"- Asked: {turn['query']} | Mentioned trials: {turn['trials']}"
        )
    return "\n".join(lines)