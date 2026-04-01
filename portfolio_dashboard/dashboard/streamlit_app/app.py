"""Portfolio Dashboard — main Streamlit entry point."""

import hashlib
import hmac
import os
import sys
from pathlib import Path

# Add dashboard root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from data_service import models

# --- Authentication ---
_PASSWORD_FILE = Path(os.environ.get("PORTFOLIO_DATA_DIR", "/data")) / ".dashboard_password"

def _load_password_hash():
    if _PASSWORD_FILE.exists():
        return _PASSWORD_FILE.read_text().strip()
    return None

def _save_password_hash(pw_hash):
    _PASSWORD_FILE.write_text(pw_hash)
    _PASSWORD_FILE.chmod(0o600)

def check_password():
    """Password gate with first-run setup. Returns True if authenticated."""
    if st.session_state.get("authenticated"):
        return True

    st.set_page_config(page_title="Login", page_icon="🔒", layout="centered")

    stored_hash = _load_password_hash()

    if stored_hash is None:
        # First run — set password
        st.title("Portfolio Dashboard Setup")
        st.info("Set a password to protect your dashboard. This is required for all future access.")
        pw1 = st.text_input("Choose a password:", type="password", key="pw_setup1")
        pw2 = st.text_input("Confirm password:", type="password", key="pw_setup2")
        if st.button("Set Password", type="primary"):
            if not pw1 or len(pw1) < 6:
                st.error("Password must be at least 6 characters")
            elif pw1 != pw2:
                st.error("Passwords don't match")
            else:
                pw_hash = hashlib.sha256(pw1.encode()).hexdigest()
                _save_password_hash(pw_hash)
                st.session_state["authenticated"] = True
                st.success("Password set! Redirecting...")
                st.rerun()
        return False

    # Check for reset token
    _RESET_FILE = Path(os.environ.get("PORTFOLIO_DATA_DIR", "/data")) / ".password_reset"
    if _RESET_FILE.exists():
        st.title("Reset Password")
        reset_token = _RESET_FILE.read_text().strip()
        token_input = st.text_input("Enter reset token:", key="reset_token_input")
        pw1 = st.text_input("New password:", type="password", key="reset_pw1")
        pw2 = st.text_input("Confirm new password:", type="password", key="reset_pw2")
        if st.button("Reset Password", type="primary"):
            if not hmac.compare_digest(token_input.strip(), reset_token):
                st.error("Invalid reset token")
            elif not pw1 or len(pw1) < 6:
                st.error("Password must be at least 6 characters")
            elif pw1 != pw2:
                st.error("Passwords don't match")
            else:
                pw_hash = hashlib.sha256(pw1.encode()).hexdigest()
                _save_password_hash(pw_hash)
                _RESET_FILE.unlink()
                st.session_state["authenticated"] = True
                st.success("Password reset! Redirecting...")
                st.rerun()
        return False

    # Normal login
    st.title("Portfolio Dashboard")
    st.markdown("---")
    password = st.text_input("Enter password:", type="password", key="pwd_input")
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Login", type="primary"):
            entered_hash = hashlib.sha256(password.encode()).hexdigest()
            if hmac.compare_digest(entered_hash, stored_hash):
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password")
    with col2:
        if st.button("Forgot password?"):
            import secrets
            token = secrets.token_urlsafe(32)
            _RESET_FILE.write_text(token)
            _RESET_FILE.chmod(0o600)
            st.info(
                "A reset token has been generated.\n\n"
                "SSH into your Pi and run:\n\n"
                f"```\ndocker exec portfolio-dashboard cat /data/.password_reset\n```\n\n"
                "Then enter the token above to reset your password."
            )
    return False

if not check_password():
    st.stop()

# --- Main app (authenticated) ---
# Initialise DB on first run
models.init_db()

st.set_page_config(
    page_title="Portfolio Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Portfolio Dashboard")
st.caption("SIP & SS ISA — Freetrade Portfolio Monitoring")

# Quick overview on main page
portfolios = models.get_portfolios()

if not portfolios:
    st.warning(
        "No portfolios loaded yet. Run:\n\n"
        "```\npython cli/import_csv.py --file ../data/portfolios.json --format json --fetch-prices --calc-risk\n```"
    )
    st.stop()

from data_service import portfolio_calc

cols = st.columns(len(portfolios))
for i, p in enumerate(portfolios):
    pid = p["id"]
    summary = portfolio_calc.calculate_portfolio_summary(pid)
    total = sum(r["market_value"] for r in summary)
    n_holdings = len(summary)

    with cols[i]:
        st.subheader(p["name"])
        st.metric("Total Value", f"{total:,.0f}")
        st.metric("Holdings", n_holdings)
        if p["last_import_date"]:
            st.caption(f"Last import: {p['last_import_date'][:10]}")

    # Show risk metrics if available
    rm = models.get_latest_risk_metrics(pid)
    if rm:
        with cols[i]:
            c1, c2 = st.columns(2)
            c1.metric("Sharpe", f"{rm['sharpe_ratio']:.2f}" if rm['sharpe_ratio'] else "N/A")
            c2.metric("Max DD", f"{rm['max_drawdown']:.1%}" if rm['max_drawdown'] else "N/A")

st.divider()
st.caption("Navigate using the sidebar pages for detailed views.")
