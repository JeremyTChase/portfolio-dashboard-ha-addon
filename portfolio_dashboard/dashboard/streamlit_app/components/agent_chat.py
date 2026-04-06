"""Reusable JezFinanceClaw chat component for any Streamlit page.

Usage at the top of any page:

    from components.agent_chat import render_chat_sidebar
    render_chat_sidebar(
        page_name="charting",
        page_context={"ticker": ticker, "timeframe": period},
    )

The component renders a chat panel in the sidebar with:
- Session picker (new chat / select / rename / delete)
- Per-session message history (loaded from the agent API)
- st.chat_input for new messages
- Per-tool-call expanders showing what the agent did
- Automatic chart_actions application (charting page only)
"""

from __future__ import annotations

from typing import Any, Optional

import streamlit as st

from agent import nemoclaw_client


# ── Chart action application (client-side) ───────────────────────────

def _apply_chart_actions(actions: list[dict]) -> None:
    """Mutate st.session_state["chart_hypotheses"] with queued chart actions."""
    if not actions:
        return
    overlays = st.session_state.setdefault("chart_hypotheses", {
        "hlines": [], "annotations": [], "positions": [],
    })
    for action in actions:
        kind = action.get("type")
        args = action.get("args", {}) or {}
        if kind == "set_ticker" and args.get("ticker"):
            st.session_state["chart_search"] = args["ticker"].upper()
        elif kind == "add_hline":
            overlays["hlines"].append({
                "price": args.get("price"),
                "label": args.get("label", ""),
                "color": args.get("color", "orange"),
            })
        elif kind == "add_annotation":
            overlays["annotations"].append({
                "date": args.get("date"),
                "text": args.get("text", ""),
            })
        elif kind == "hypothetical_position":
            overlays["positions"].append({
                "action": args.get("action"),
                "shares": args.get("shares"),
                "price": args.get("price"),
                "note": args.get("note", ""),
            })
        elif kind == "clear_overlays":
            st.session_state["chart_hypotheses"] = {
                "hlines": [], "annotations": [], "positions": [],
            }


# ── Session state helpers ────────────────────────────────────────────

_SESS_ID_KEY = "agent_active_session_id"
_SESS_LIST_KEY = "agent_session_list"


def _refresh_session_list() -> list[dict]:
    try:
        sessions = nemoclaw_client.list_sessions(limit=50)
    except Exception as e:
        st.sidebar.error(f"Agent API: {e}")
        sessions = []
    st.session_state[_SESS_LIST_KEY] = sessions
    return sessions


def _ensure_session(page_name: str) -> Optional[int]:
    """Make sure there's an active session. Returns its id or None on failure."""
    sid = st.session_state.get(_SESS_ID_KEY)
    if sid:
        return sid

    sessions = st.session_state.get(_SESS_LIST_KEY) or _refresh_session_list()
    if sessions:
        st.session_state[_SESS_ID_KEY] = sessions[0]["id"]
        return sessions[0]["id"]

    # No sessions exist — create the first one
    try:
        created = nemoclaw_client.create_session(title="New chat", page_context=page_name)
        st.session_state[_SESS_ID_KEY] = created["session_id"]
        _refresh_session_list()
        return created["session_id"]
    except Exception as e:
        st.sidebar.error(f"Could not create chat session: {e}")
        return None


# ── Renderers ────────────────────────────────────────────────────────

def _render_session_picker(page_name: str) -> Optional[int]:
    sessions = st.session_state.get(_SESS_LIST_KEY)
    if sessions is None:
        sessions = _refresh_session_list()

    cols = st.sidebar.columns([3, 1])
    with cols[0]:
        if st.button("➕ New chat", key="agent_new_chat", use_container_width=True):
            try:
                created = nemoclaw_client.create_session(title="New chat", page_context=page_name)
                st.session_state[_SESS_ID_KEY] = created["session_id"]
                _refresh_session_list()
                st.rerun()
            except Exception as e:
                st.sidebar.error(str(e))
    with cols[1]:
        if st.button("⟳", key="agent_refresh", help="Refresh session list",
                     use_container_width=True):
            _refresh_session_list()
            st.rerun()

    if not sessions:
        return _ensure_session(page_name)

    options = {f"{s['title']}  ·  {s['updated_at'][5:16]}": s["id"] for s in sessions}
    current_id = st.session_state.get(_SESS_ID_KEY) or sessions[0]["id"]
    current_label = next((k for k, v in options.items() if v == current_id), list(options.keys())[0])

    selected_label = st.sidebar.selectbox(
        "Chat", list(options.keys()),
        index=list(options.keys()).index(current_label),
        key="agent_session_select",
    )
    selected_id = options[selected_label]
    if selected_id != current_id:
        st.session_state[_SESS_ID_KEY] = selected_id
        st.rerun()

    # Rename / delete
    with st.sidebar.expander("Manage chat"):
        new_title = st.text_input("Rename", value=next(s["title"] for s in sessions if s["id"] == selected_id),
                                  key=f"agent_rename_{selected_id}")
        rcols = st.columns(2)
        with rcols[0]:
            if st.button("Save title", key=f"agent_save_title_{selected_id}", use_container_width=True):
                try:
                    nemoclaw_client.rename_session(selected_id, new_title)
                    _refresh_session_list()
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        with rcols[1]:
            if st.button("🗑 Delete", key=f"agent_delete_{selected_id}", use_container_width=True):
                try:
                    nemoclaw_client.delete_session(selected_id)
                    st.session_state.pop(_SESS_ID_KEY, None)
                    _refresh_session_list()
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    return selected_id


def _render_messages(session_id: int) -> None:
    try:
        messages = nemoclaw_client.get_messages(session_id)
    except Exception as e:
        st.error(f"Could not load messages: {e}")
        return

    for m in messages:
        role = m.get("role")
        if role == "user":
            with st.chat_message("user"):
                st.markdown(m.get("content") or "")
        elif role == "assistant":
            content = m.get("content") or ""
            tool_calls = m.get("tool_calls")
            if content or not tool_calls:
                with st.chat_message("assistant"):
                    if content:
                        st.markdown(content)
                    if tool_calls:
                        with st.expander(f"🔧 Called {len(tool_calls)} tool(s)"):
                            for tc in tool_calls:
                                fn = tc.get("function", {})
                                st.code(f"{fn.get('name')}({fn.get('arguments', '{}')})", language="json")
        # tool messages are folded into the assistant expander above; skip rendering them on their own


def _render_input(session_id: int, page_name: str, page_context: Optional[dict]) -> None:
    user_text = st.chat_input("Ask JezFinanceClaw…", key=f"agent_input_{session_id}")
    if not user_text:
        return

    with st.chat_message("user"):
        st.markdown(user_text)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                result = nemoclaw_client.turn(
                    session_id=session_id,
                    message=user_text,
                    page=page_name,
                    page_context=page_context,
                )
            except Exception as e:
                st.error(f"Agent error: {e}")
                return

        st.markdown(result.get("reply") or "_(no reply)_")

        tool_calls = result.get("tool_calls") or []
        if tool_calls:
            with st.expander(f"🔧 {len(tool_calls)} tool call(s) · {result.get('duration_ms', 0)} ms"):
                for tc in tool_calls:
                    icon = "✓" if tc.get("ok") else "✗"
                    st.markdown(f"**{icon} `{tc['name']}`** — {tc.get('summary', '')}")
                    if tc.get("args"):
                        st.json(tc["args"], expanded=False)

        chart_actions = result.get("chart_actions") or []
        if chart_actions:
            _apply_chart_actions(chart_actions)
            st.success(f"Applied {len(chart_actions)} chart action(s) — chart will update on next render.")

    _refresh_session_list()
    # Trigger rerun so the message is persisted-and-redrawn from the API on next paint
    st.rerun()


# ── Public entrypoint ────────────────────────────────────────────────

def render_chat_sidebar(
    page_name: str,
    page_context: Optional[dict] = None,
) -> None:
    """Drop this at the top of any Streamlit page to add the agent chat panel."""
    if not nemoclaw_client.is_available():
        with st.sidebar:
            st.divider()
            st.subheader("💬 JezFinanceClaw")
            st.caption("Agent API offline. Check the nemoclaw add-on is running.")
        return

    with st.sidebar:
        st.divider()
        st.subheader("💬 JezFinanceClaw")
        st.caption(f"Page context: `{page_name}`")

    session_id = _render_session_picker(page_name)
    if not session_id:
        return

    with st.sidebar:
        st.markdown("---")
        # Render the message history + input inside the sidebar via a container
        chat_container = st.container(height=520)
        with chat_container:
            _render_messages(session_id)
            _render_input(session_id, page_name, page_context)
