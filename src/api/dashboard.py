"""Web dashboard for monitoring bot stats.

Provides a browser-based dashboard with system stats, user analytics,
cost tracking, and session monitoring.
"""

import secrets
import time
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from ..config.settings import Settings
from ..storage.database import DatabaseManager

logger = structlog.get_logger()

# Boot time for uptime calculation
_BOOT_TIME = time.time()


def _check_basic_auth(request: Request, settings: Settings) -> bool:
    """Verify basic auth credentials from settings."""
    if not settings.dashboard_username or not settings.dashboard_password:
        # No auth configured — allow access (dev mode)
        return True

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False

    import base64

    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        return False

    return secrets.compare_digest(
        username, settings.dashboard_username
    ) and secrets.compare_digest(password, settings.dashboard_password)


def create_dashboard_router(
    db_manager: DatabaseManager,
    settings: Settings,
) -> APIRouter:
    """Create the dashboard API router."""

    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    async def _require_auth(request: Request) -> None:
        if not _check_basic_auth(request, settings):
            raise HTTPException(
                status_code=401,
                detail="Unauthorized",
                headers={"WWW-Authenticate": 'Basic realm="Dashboard"'},
            )

    # ------------------------------------------------------------------
    # HTML page
    # ------------------------------------------------------------------
    @router.get("", response_class=HTMLResponse)
    async def dashboard_page(request: Request) -> HTMLResponse:
        await _require_auth(request)
        return HTMLResponse(content=DASHBOARD_HTML)

    # ------------------------------------------------------------------
    # JSON API endpoints
    # ------------------------------------------------------------------
    @router.get("/api/stats")
    async def dashboard_stats(request: Request) -> JSONResponse:
        await _require_auth(request)

        async with db_manager.get_connection() as conn:
            # Total messages
            cursor = await conn.execute("SELECT COUNT(*) FROM messages")
            total_messages = (await cursor.fetchone())[0] or 0

            # Total users
            cursor = await conn.execute("SELECT COUNT(*) FROM users")
            total_users = (await cursor.fetchone())[0] or 0

            # Active users (last 7 days)
            cursor = await conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM messages "
                "WHERE timestamp > datetime('now', '-7 days')"
            )
            active_users = (await cursor.fetchone())[0] or 0

            # Total cost
            cursor = await conn.execute("SELECT COALESCE(SUM(cost), 0) FROM messages")
            total_cost = (await cursor.fetchone())[0] or 0.0

            # Messages today
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM messages "
                "WHERE date(timestamp) = date('now')"
            )
            messages_today = (await cursor.fetchone())[0] or 0

            # Cost today
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(cost), 0) FROM messages "
                "WHERE date(timestamp) = date('now')"
            )
            cost_today = (await cursor.fetchone())[0] or 0.0

            # Active sessions
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE is_active = TRUE"
            )
            active_sessions = (await cursor.fetchone())[0] or 0

            uptime_seconds = int(time.time() - _BOOT_TIME)

        return JSONResponse(
            {
                "total_messages": total_messages,
                "total_users": total_users,
                "active_users_7d": active_users,
                "total_cost": round(total_cost, 4),
                "messages_today": messages_today,
                "cost_today": round(cost_today, 4),
                "active_sessions": active_sessions,
                "uptime_seconds": uptime_seconds,
            }
        )

    @router.get("/api/users")
    async def dashboard_users(request: Request) -> JSONResponse:
        await _require_auth(request)

        async with db_manager.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT
                    u.user_id,
                    u.telegram_username,
                    u.message_count,
                    u.total_cost,
                    u.last_active,
                    u.session_count,
                    u.is_allowed
                FROM users u
                ORDER BY u.total_cost DESC
                """
            )
            rows = await cursor.fetchall()

        users = []
        for row in rows:
            d = dict(row)
            # Ensure serialisable
            if d.get("last_active"):
                d["last_active"] = str(d["last_active"])
            users.append(d)

        return JSONResponse({"users": users})

    @router.get("/api/costs")
    async def dashboard_costs(request: Request) -> JSONResponse:
        await _require_auth(request)

        async with db_manager.get_connection() as conn:
            # Daily costs (last 30 days)
            cursor = await conn.execute(
                """
                SELECT
                    date(timestamp) as date,
                    COALESCE(SUM(cost), 0) as total_cost,
                    COUNT(*) as request_count,
                    COUNT(DISTINCT user_id) as active_users
                FROM messages
                WHERE timestamp >= datetime('now', '-30 days')
                GROUP BY date(timestamp)
                ORDER BY date ASC
                """
            )
            daily = [dict(r) for r in await cursor.fetchall()]

            # Weekly costs
            cursor = await conn.execute(
                """
                SELECT
                    strftime('%Y-W%W', timestamp) as week,
                    COALESCE(SUM(cost), 0) as total_cost,
                    COUNT(*) as request_count
                FROM messages
                WHERE timestamp >= datetime('now', '-90 days')
                GROUP BY strftime('%Y-W%W', timestamp)
                ORDER BY week ASC
                """
            )
            weekly = [dict(r) for r in await cursor.fetchall()]

            # Cost by user
            cursor = await conn.execute(
                """
                SELECT
                    u.user_id,
                    u.telegram_username,
                    COALESCE(SUM(m.cost), 0) as total_cost,
                    COUNT(m.message_id) as message_count
                FROM users u
                LEFT JOIN messages m ON u.user_id = m.user_id
                GROUP BY u.user_id
                ORDER BY total_cost DESC
                LIMIT 20
                """
            )
            by_user = [dict(r) for r in await cursor.fetchall()]

        return JSONResponse(
            {
                "daily": daily,
                "weekly": weekly,
                "by_user": by_user,
            }
        )

    @router.get("/api/sessions")
    async def dashboard_sessions(request: Request) -> JSONResponse:
        await _require_auth(request)

        async with db_manager.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT
                    s.session_id,
                    s.user_id,
                    u.telegram_username,
                    s.project_path,
                    s.created_at,
                    s.last_used,
                    s.total_cost,
                    s.message_count,
                    s.is_active
                FROM sessions s
                LEFT JOIN users u ON s.user_id = u.user_id
                ORDER BY s.last_used DESC
                LIMIT 50
                """
            )
            rows = await cursor.fetchall()

        sessions = []
        for row in rows:
            d = dict(row)
            for k in ("created_at", "last_used"):
                if d.get(k):
                    d[k] = str(d[k])
            sessions.append(d)

        return JSONResponse({"sessions": sessions})

    return router


# ---------------------------------------------------------------------------
# Dashboard HTML (single-page, embedded CSS + JS, Chart.js from CDN)
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Claude Code Telegram - Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#0f1117;--card:#1a1d2e;--border:#2a2d3e;--text:#e0e0e0;--muted:#888;--accent:#6c63ff;--green:#00c853;--red:#ff5252;--orange:#ffab40}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.header{background:var(--card);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:20px;font-weight:600}
.header .meta{color:var(--muted);font-size:13px}
.container{max-width:1400px;margin:0 auto;padding:24px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px}
.card .label{font-size:12px;text-transform:uppercase;color:var(--muted);letter-spacing:.5px;margin-bottom:8px}
.card .value{font-size:28px;font-weight:700}
.card .sub{font-size:12px;color:var(--muted);margin-top:4px}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}
@media(max-width:900px){.charts{grid-template-columns:1fr}}
.chart-box{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px}
.chart-box h3{font-size:14px;margin-bottom:12px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-weight:500;text-transform:uppercase;font-size:11px;letter-spacing:.5px}
.table-box{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:24px;overflow-x:auto}
.table-box h3{font-size:14px;margin-bottom:12px;color:var(--muted)}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
.badge-active{background:rgba(0,200,83,.15);color:var(--green)}
.badge-inactive{background:rgba(255,82,82,.15);color:var(--red)}
.refresh-note{text-align:center;color:var(--muted);font-size:12px;margin-top:12px}
</style>
</head>
<body>
<div class="header">
  <h1>Claude Code Telegram Dashboard</h1>
  <span class="meta" id="uptime">loading...</span>
</div>
<div class="container">
  <!-- Overview cards -->
  <div class="cards">
    <div class="card"><div class="label">Total Users</div><div class="value" id="c-users">-</div></div>
    <div class="card"><div class="label">Active Sessions</div><div class="value" id="c-sessions">-</div></div>
    <div class="card"><div class="label">Messages Today</div><div class="value" id="c-msgs">-</div></div>
    <div class="card"><div class="label">Cost Today</div><div class="value" id="c-cost">-</div><div class="sub" id="c-cost-total"></div></div>
  </div>

  <!-- Charts -->
  <div class="charts">
    <div class="chart-box"><h3>Messages (Last 7 Days)</h3><canvas id="chartMessages"></canvas></div>
    <div class="chart-box"><h3>Cost by User</h3><canvas id="chartCost"></canvas></div>
  </div>

  <!-- Sessions table -->
  <div class="table-box">
    <h3>Recent Sessions</h3>
    <table><thead><tr><th>User</th><th>Project</th><th>Started</th><th>Messages</th><th>Cost</th><th>Status</th></tr></thead><tbody id="t-sessions"></tbody></table>
  </div>

  <!-- Top users table -->
  <div class="table-box">
    <h3>Top Users by Usage</h3>
    <table><thead><tr><th>User</th><th>Messages</th><th>Sessions</th><th>Total Cost</th><th>Last Active</th></tr></thead><tbody id="t-users"></tbody></table>
  </div>

  <div class="refresh-note">Auto-refreshes every 30 seconds</div>
</div>

<script>
const BASE = window.location.pathname.replace(/\/+$/, '');
let msgChart = null, costChart = null;

function fmt$(v){return '$' + (v||0).toFixed(4)}
function fmtTime(s){if(!s)return'-';const d=new Date(s);return d.toLocaleString()}
function fmtUptime(s){const h=Math.floor(s/3600),m=Math.floor((s%3600)/60);return 'Uptime: '+h+'h '+m+'m'}

async function fetchJSON(path){
  const r = await fetch(BASE + path);
  if(!r.ok) throw new Error(r.statusText);
  return r.json();
}

async function loadStats(){
  try{
    const s = await fetchJSON('/api/stats');
    document.getElementById('c-users').textContent = s.total_users;
    document.getElementById('c-sessions').textContent = s.active_sessions;
    document.getElementById('c-msgs').textContent = s.messages_today;
    document.getElementById('c-cost').textContent = fmt$(s.cost_today);
    document.getElementById('c-cost-total').textContent = 'Total: ' + fmt$(s.total_cost);
    document.getElementById('uptime').textContent = fmtUptime(s.uptime_seconds);
  }catch(e){console.error('stats',e)}
}

async function loadCharts(){
  try{
    const c = await fetchJSON('/api/costs');
    // Messages chart (last 7 days)
    const last7 = (c.daily||[]).slice(-7);
    const labels = last7.map(d=>d.date);
    const msgData = last7.map(d=>d.request_count);
    const costData = last7.map(d=>d.total_cost);

    if(msgChart) msgChart.destroy();
    msgChart = new Chart(document.getElementById('chartMessages'),{
      type:'line',
      data:{labels, datasets:[
        {label:'Messages',data:msgData,borderColor:'#6c63ff',backgroundColor:'rgba(108,99,255,.1)',fill:true,tension:.3},
        {label:'Cost ($)',data:costData,borderColor:'#ffab40',backgroundColor:'rgba(255,171,64,.1)',fill:true,tension:.3,yAxisID:'y1'}
      ]},
      options:{responsive:true,interaction:{mode:'index',intersect:false},scales:{
        y:{beginAtZero:true,ticks:{color:'#888'},grid:{color:'#2a2d3e'}},
        y1:{position:'right',beginAtZero:true,ticks:{color:'#888',callback:v=>'$'+v.toFixed(2)},grid:{drawOnChartArea:false}},
        x:{ticks:{color:'#888'},grid:{color:'#2a2d3e'}}
      },plugins:{legend:{labels:{color:'#e0e0e0'}}}}
    });

    // Cost by user chart
    const byUser = (c.by_user||[]).filter(u=>u.total_cost>0).slice(0,10);
    if(costChart) costChart.destroy();
    costChart = new Chart(document.getElementById('chartCost'),{
      type:'bar',
      data:{labels:byUser.map(u=>u.telegram_username||('User '+u.user_id)),datasets:[{
        label:'Total Cost ($)',data:byUser.map(u=>u.total_cost),
        backgroundColor:'rgba(108,99,255,.7)',borderRadius:6
      }]},
      options:{responsive:true,indexAxis:'y',scales:{
        x:{beginAtZero:true,ticks:{color:'#888',callback:v=>'$'+v.toFixed(2)},grid:{color:'#2a2d3e'}},
        y:{ticks:{color:'#888'},grid:{color:'#2a2d3e'}}
      },plugins:{legend:{display:false}}}
    });
  }catch(e){console.error('charts',e)}
}

async function loadSessions(){
  try{
    const s = await fetchJSON('/api/sessions');
    const tbody = document.getElementById('t-sessions');
    tbody.innerHTML = (s.sessions||[]).slice(0,15).map(r=>`<tr>
      <td>${r.telegram_username||r.user_id}</td>
      <td>${(r.project_path||'').split('/').pop()||r.project_path}</td>
      <td>${fmtTime(r.created_at)}</td>
      <td>${r.message_count||0}</td>
      <td>${fmt$(r.total_cost)}</td>
      <td><span class="badge ${r.is_active?'badge-active':'badge-inactive'}">${r.is_active?'Active':'Inactive'}</span></td>
    </tr>`).join('');
  }catch(e){console.error('sessions',e)}
}

async function loadUsers(){
  try{
    const u = await fetchJSON('/api/users');
    const tbody = document.getElementById('t-users');
    tbody.innerHTML = (u.users||[]).slice(0,15).map(r=>`<tr>
      <td>${r.telegram_username||r.user_id}</td>
      <td>${r.message_count||0}</td>
      <td>${r.session_count||0}</td>
      <td>${fmt$(r.total_cost)}</td>
      <td>${fmtTime(r.last_active)}</td>
    </tr>`).join('');
  }catch(e){console.error('users',e)}
}

async function refresh(){
  await Promise.all([loadStats(), loadCharts(), loadSessions(), loadUsers()]);
}
refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>
"""
