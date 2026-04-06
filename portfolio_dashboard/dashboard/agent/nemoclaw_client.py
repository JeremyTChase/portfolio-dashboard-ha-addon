"""HTTP client for the JezFinanceClaw agent API.

The dashboard never imports nemoclaw directly — it only talks to the
agent_api FastAPI service running inside the JezFinanceClaw container
on the same Pi (host_network).
"""

from __future__ import annotations

import os
from typing import Any, Optional

import requests


def _base_url() -> str:
    return os.environ.get("AGENT_API_URL", "http://127.0.0.1:18792").rstrip("/")


def _headers() -> dict:
    key = os.environ.get("AGENT_API_KEY", "")
    h = {"Content-Type": "application/json"}
    if key:
        h["X-API-Key"] = key
    return h


# Per-request timeouts: (connect, read).
# Read is generous because optimize / consider / stress_test can take 60-300s.
_TIMEOUT_FAST = (5, 15)
_TIMEOUT_TURN = (10, 360)


class AgentAPIError(RuntimeError):
    pass


def _request(method: str, path: str, json_body: Optional[dict] = None,
             timeout=_TIMEOUT_FAST) -> Any:
    url = f"{_base_url()}{path}"
    try:
        resp = requests.request(method, url, json=json_body,
                                headers=_headers(), timeout=timeout)
    except requests.ConnectionError as e:
        raise AgentAPIError(
            f"Cannot reach JezFinanceClaw agent at {url} — is the nemoclaw add-on running?"
        ) from e
    except requests.Timeout as e:
        raise AgentAPIError(f"Agent request timed out after {timeout[1]}s ({path})") from e

    if resp.status_code == 401:
        raise AgentAPIError("Agent rejected API key — check AGENT_API_KEY in dashboard options")
    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text[:200])
        except Exception:
            detail = resp.text[:200]
        raise AgentAPIError(f"Agent error {resp.status_code}: {detail}")
    if resp.text:
        return resp.json()
    return None


# ── Health ───────────────────────────────────────────────────────────

def health() -> dict:
    return _request("GET", "/agent/health")


def is_available() -> bool:
    try:
        health()
        return True
    except Exception:
        return False


# ── Sessions ─────────────────────────────────────────────────────────

def create_session(title: str = "New chat", page_context: Optional[str] = None) -> dict:
    return _request("POST", "/agent/sessions", json_body={
        "title": title, "source": "dashboard", "page_context": page_context,
    })


def list_sessions(limit: int = 50) -> list[dict]:
    return _request("GET", f"/agent/sessions?source=dashboard&limit={limit}") or []


def get_session(session_id: int) -> dict:
    return _request("GET", f"/agent/sessions/{session_id}")


def rename_session(session_id: int, title: str) -> None:
    _request("PATCH", f"/agent/sessions/{session_id}", json_body={"title": title})


def delete_session(session_id: int) -> None:
    _request("DELETE", f"/agent/sessions/{session_id}")


def get_messages(session_id: int) -> list[dict]:
    data = _request("GET", f"/agent/sessions/{session_id}/messages")
    return (data or {}).get("messages", [])


# ── Turn ─────────────────────────────────────────────────────────────

def turn(
    session_id: int,
    message: str,
    page: Optional[str] = None,
    page_context: Optional[dict] = None,
) -> dict:
    """Run one user turn. Returns: {reply, tool_calls, chart_actions, iterations, duration_ms}."""
    return _request(
        "POST",
        f"/agent/sessions/{session_id}/turn",
        json_body={
            "message": message,
            "page": page,
            "page_context": page_context,
            "source": "dashboard",
            "auto_title_if_first": True,
        },
        timeout=_TIMEOUT_TURN,
    )
