"""
Deliverable 2 - Admin Dashboard
=================================
A lightweight admin page and JSON API for monitoring the Socratic Oracle
deployment in real time.

What this does:
    Exposes two routes:
      /admin/dashboard  -- a self-contained HTML page (no JS framework)
                           that auto-refreshes every 5 seconds and shows
                           active sessions, inference load, and queue depth.
      /admin/api/stats  -- raw JSON endpoint for programmatic access or
                           for wiring up a fancier frontend later.

What I learned:
    - You do not need React or Vue for a monitoring page. A single HTML
      string with a <meta refresh> tag and some inline CSS is perfectly
      adequate when the audience is one admin checking on a pilot.
    - FastAPI's APIRouter makes it trivial to bolt on a whole sub-app
      without touching the main file -- just include_router() and done.
    - Returning HTMLResponse with an f-string template is quick and dirty,
      but for anything beyond a single dashboard page you should use
      Jinja2 templates.

Author: Akshay T P
Date: March 2025
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.deliv2_session_manager import SessionManager

# ---------------------------------------------------------------------------
# DESIGN DECISION: Inline HTML vs Jinja2 vs separate frontend (React/Vue)
# ---------------------------------------------------------------------------
# We chose inline HTML returned as an f-string.
#
# Alternative 1 - Jinja2 templates:
#   Pros:  cleaner separation of logic and presentation, easier to maintain
#          as the page grows, supports template inheritance.
#   Cons:  adds a dependency (jinja2) and a templates/ directory.  For a
#          single dashboard page this is over-engineering.
#
# Alternative 2 - Separate React/Vue SPA:
#   Pros:  real-time charts, interactive filtering, modern look.
#   Cons:  requires a build step, node_modules, and a deployment pipeline.
#          Completely disproportionate for a pilot admin panel.
#
# Alternative 3 - Grafana + Prometheus:
#   Pros:  industry-standard monitoring, beautiful out-of-the-box charts,
#          alerting, and historical data.
#   Cons:  two additional services to deploy and configure.  Makes sense
#          at production scale, not for a 250-student pilot on HPC.
#
# Verdict: inline HTML.  It works, it is self-contained, and someone
#          picking up the codebase can read everything in one file.
# ---------------------------------------------------------------------------


# The router needs a reference to the SessionManager instance.  This is
# set at startup by calling init_dashboard(session_manager).
_session_manager: "SessionManager" = None  # type: ignore


def init_dashboard(session_manager: "SessionManager") -> None:
    """
    Inject the SessionManager dependency.  Called once during app startup.
    """
    global _session_manager
    _session_manager = session_manager


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/api/stats", response_class=JSONResponse)
async def get_stats():
    """
    Return current system metrics as JSON.

    Response shape:
    {
        "active_sessions": int,
        "active_inferences": int,
        "max_inferences": int,
        "queue_depth": int,
        "estimated_wait_sec": float,
        "avg_latency_sec": float,
        "sessions": [ ... ]   # per-session details
    }
    """
    if _session_manager is None:
        return JSONResponse(
            {"error": "Dashboard not initialized"},
            status_code=503
        )

    stats = await _session_manager.get_stats()
    sessions = await _session_manager.list_sessions()
    stats["sessions"] = sessions
    return stats


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """
    Serve a self-contained HTML admin dashboard.

    The page auto-refreshes every 5 seconds via a <meta> tag.  No
    JavaScript frameworks are required -- just plain HTML and inline CSS.
    """
    if _session_manager is None:
        return HTMLResponse("<h1>Dashboard not initialized</h1>", status_code=503)

    stats = await _session_manager.get_stats()
    sessions = await _session_manager.list_sessions()

    # -- Build the sessions table rows --
    session_rows = ""
    if sessions:
        for s in sessions:
            session_rows += f"""
            <tr>
                <td><code>{s['session_id'][:8]}...</code></td>
                <td>{s['created_at']}</td>
                <td>{s['last_active']}</td>
                <td>{s['state']}</td>
                <td>{s['message_count']}</td>
            </tr>"""
    else:
        session_rows = """
        <tr>
            <td colspan="5" style="text-align:center; color:#888;">
                No active sessions
            </td>
        </tr>"""

    # -- Render the full page --
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="5">
    <title>Socratic Oracle -- Admin Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',
                         Roboto, Helvetica, Arial, sans-serif;
            background: #f5f5f5;
            color: #333;
            padding: 2rem;
        }}
        h1 {{
            font-size: 1.5rem;
            margin-bottom: 0.25rem;
        }}
        .subtitle {{
            font-size: 0.85rem;
            color: #888;
            margin-bottom: 1.5rem;
        }}
        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .card {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 6px;
            padding: 1.25rem;
        }}
        .card .label {{
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #888;
            margin-bottom: 0.25rem;
        }}
        .card .value {{
            font-size: 1.75rem;
            font-weight: 600;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 6px;
            overflow: hidden;
        }}
        th, td {{
            text-align: left;
            padding: 0.6rem 1rem;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #fafafa;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #666;
        }}
        code {{
            font-size: 0.85rem;
            background: #f0f0f0;
            padding: 0.15rem 0.3rem;
            border-radius: 3px;
        }}
        .footer {{
            margin-top: 1.5rem;
            font-size: 0.75rem;
            color: #aaa;
        }}
    </style>
</head>
<body>
    <h1>Socratic Oracle -- Admin Dashboard</h1>
    <p class="subtitle">Auto-refreshes every 5 seconds</p>

    <div class="cards">
        <div class="card">
            <div class="label">Active Sessions</div>
            <div class="value">{stats['active_sessions']}</div>
        </div>
        <div class="card">
            <div class="label">Inference Slots</div>
            <div class="value">{stats['active_inferences']} / {stats['max_inferences']}</div>
        </div>
        <div class="card">
            <div class="label">Queue Depth</div>
            <div class="value">{stats['queue_depth']}</div>
        </div>
        <div class="card">
            <div class="label">Est. Wait</div>
            <div class="value">{stats['estimated_wait_sec']}s</div>
        </div>
        <div class="card">
            <div class="label">Avg Latency</div>
            <div class="value">{stats['avg_latency_sec']}s</div>
        </div>
    </div>

    <h2 style="font-size:1.1rem; margin-bottom:0.75rem;">Active Sessions</h2>
    <table>
        <thead>
            <tr>
                <th>Session ID</th>
                <th>Created</th>
                <th>Last Active</th>
                <th>State</th>
                <th>Messages</th>
            </tr>
        </thead>
        <tbody>
            {session_rows}
        </tbody>
    </table>

    <p class="footer">
        Concurrency cap: {stats['max_inferences']} simultaneous inferences.
        Page generated server-side; no client-side JS required.
    </p>
</body>
</html>"""

    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# FUTURE IMPROVEMENTS (if we had more time)
# ---------------------------------------------------------------------------
# 1. WebSocket-based live updates:
#    Replace the meta-refresh with a WebSocket that pushes stats every
#    second.  Gives a smoother real-time feel without full page reloads.
#
# 2. Historical charts:
#    Log stats to a time-series store (InfluxDB, or even a rotating JSON
#    file) and render sparklines / charts on the dashboard so the admin
#    can see trends (e.g. peak usage at 2pm on Tuesdays).
#
# 3. Authentication:
#    Right now anyone who knows the URL can view the dashboard.  Adding
#    HTTP Basic Auth or an API-key check would be trivial and important
#    before any real deployment.
#
# 4. Session management actions:
#    Let the admin forcibly end a stale session or bump a queued request
#    to the front, directly from the dashboard.
#
# 5. Grafana integration:
#    Expose a /metrics endpoint in Prometheus format and point Grafana at
#    it.  This gives you alerting, historical dashboards, and anomaly
#    detection for free.
# ---------------------------------------------------------------------------
