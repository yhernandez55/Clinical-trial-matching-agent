# app/fast_api_app.py
"""
FastAPI entry point for the clinical trial matching agent.
Uses ADK's get_fast_api_app helper for session management,
routing, and the built-in chat interface.
"""
# Imoport libraries:
import os
import uvicorn
from google.adk.cli.fast_api import get_fast_api_app

# BASE_DIR is the parent of the app/ package — ADK scans it to discover
# the app/ agent package (which exposes root_agent via __init__.py)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Session database — SQLite kept local, no external persistence
SESSION_DB_URL = f"sqlite:///{os.path.join(BASE_DIR, 'sessions.db')}"

# Create the FastAPI app using ADK's helper
# This automatically wires up /chat, /sessions, and the ADK web UI
app = get_fast_api_app(
    agent_dir=BASE_DIR,
    session_db_url=SESSION_DB_URL,
    allow_origins=["*"],  # Restrict in production
    web=True,             # Enables ADK's built-in chat UI for demo/video
)

# Health check endpoint:
@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "agent": "clinical-trial-matching"}

# Main entry point:
if __name__ == "__main__":
    uvicorn.run(
        "app.fast_api_app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Keep False — reload conflicts with MCP subprocess management
    )
