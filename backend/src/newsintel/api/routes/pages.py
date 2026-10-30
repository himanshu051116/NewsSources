# ruff: noqa: E501
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from newsintel.api.dependencies import AccessAdminAuth, AuthenticatedUserDependency, ViewerAuth
from newsintel.api.ui import BASE_CSS, COMMON_JS, render_app_page
from newsintel.domain.access import AccessStatus, Permission, role_has_permission

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
async def landing() -> str:
    return _page(
        "News Intelligence Platform",
        """
        <section class="hero">
          <p class="eyebrow">Private research platform</p>
          <h1>Understand the story behind the headline.</h1>
          <p class="lead">Follow live reporting, compare accounts and trace each development back to its sources.</p>
          <div class="actions">
            <a class="button" href="/auth/login">Sign in</a>
            <a class="button secondary" href="/sign-in">Access details</a>
          </div>
        </section>
        <section class="band">
          <div>
            <h2>Approval based access</h2>
            <p>Anyone with a verified identity can sign in. New accounts are placed in a pending queue until the platform owner approves access.</p>
          </div>
          <div>
            <h2>Follow the evidence</h2>
            <p>Read current reporting alongside earlier coverage, corrections and source-linked explanations. What is uncertain stays visible.</p>
          </div>
        </section>
        """,
    )


@router.get("/sign-in", response_class=HTMLResponse)
async def sign_in(request: Request) -> str:
    settings = request.app.state.settings
    configured = settings.auth_mode == "oidc" or (
        settings.dev_auth_bypass_enabled and settings.environment != "production"
    )
    detail = (
        "Use your verified identity provider account. Your first sign-in creates one access request automatically."
        if configured
        else "Sign-in is not configured for this local checkout yet."
    )
    return _page(
        "Sign In",
        f"""
        <section class="panel narrow">
          <h1>Sign in</h1>
          <p>{detail}</p>
          <a class="button" href="/auth/login">Continue</a>
          <p class="muted">No extra request form is needed. If your account is pending, you will see its current status after signing in.</p>
        </section>
        """,
    )


@router.get("/pending", response_class=HTMLResponse)
async def pending(user: AuthenticatedUserDependency) -> str:
    submitted = user.requested_at.strftime("%Y-%m-%d %H:%M UTC")
    status_label = user.access_status.value.replace("_", " ").title()
    return _page(
        "Access Pending",
        f"""
        <section class="panel narrow">
          <p class="eyebrow">Access request</p>
          <h1>{status_label}</h1>
          <p>Your access request was submitted on {submitted}. The owner will review it. You do not need to submit another request.</p>
          <dl>
            <dt>Account</dt><dd>{_safe(user.verified_email or user.display_name or user.auth_provider_user_id)}</dd>
            <dt>Status</dt><dd>{status_label}</dd>
          </dl>
          <a class="button secondary" href="/auth/logout">Log out</a>
        </section>
        """,
    )


@router.get("/access-denied", response_class=HTMLResponse)
async def access_denied(user: AuthenticatedUserDependency) -> str:
    reason = {
        AccessStatus.REJECTED: user.rejection_reason or "This account was not approved.",
        AccessStatus.SUSPENDED: user.suspension_reason or "This account is currently suspended.",
        AccessStatus.REVOKED: user.revocation_reason or "This account no longer has access.",
        AccessStatus.EXPIRED: "This account's temporary access has expired.",
    }.get(user.access_status, "This account cannot access the application right now.")
    return _page(
        "Access Unavailable",
        f"""
        <section class="panel narrow">
          <p class="eyebrow">Account status</p>
          <h1>Access unavailable</h1>
          <p>{_safe(reason)}</p>
          <a class="button secondary" href="/auth/logout">Log out</a>
        </section>
        """,
    )


@router.get("/app", response_class=HTMLResponse)
async def app_home(user: ViewerAuth) -> str:
    role = user.role
    role_value = role.value
    quick_links = [
        '<a class="tile" href="/briefs"><div class="eyebrow">Two minutes</div><h2>Your daily & weekly brief</h2><p class="muted">Headlines and one-line excerpts across publishers. Save a stream around your interests.</p></a>',
        '<a class="tile" href="/search"><div class="eyebrow">Find</div><h2>Find a story or event</h2><p class="muted">Find events, reporting and claims across the archive.</p></a>',
        '<a class="tile" href="/events"><div class="eyebrow">Investigate</div><h2>Track an event</h2><p class="muted">Read the timeline and compare accounts from different sources.</p></a>',
        '<a class="tile" href="/news"><div class="eyebrow">Read</div><h2>Latest reporting</h2><p class="muted">Read fresh reports and inspect their original sources.</p></a>',
    ]
    if role_has_permission(role, Permission.CLAIMS_VIEW):
        quick_links.extend(
            [
                '<a class="tile" href="/investigations"><div class="eyebrow">Workspace</div><h2>Investigations</h2><p class="muted">Return to tracked cases, watchlists, saved searches and analyst notes.</p></a>',
                '<a class="tile" href="/historical-research"><div class="eyebrow">Research</div><h2>History and archives</h2><p class="muted">Find earlier coverage and see what changed over time.</p></a>',
            ]
        )
    if role_has_permission(role, Permission.SOURCES_MANAGE):
        quick_links.append(
            '<a class="tile" href="/news-sources"><div class="eyebrow">Operations</div><h2>Source monitoring</h2><p class="muted">Review publisher feeds, failed fetches and capture quality.</p></a>'
        )
    analyst_workspace_panel = (
        """<section class="panel" style="margin-top:18px"><div class="section-head"><div><h2>My analyst workspace</h2><div class="muted small">Persistent cases and monitored changes.</div></div><a class="small" href="/investigations">Open investigations</a></div><div class="grid four"><div class="metric"><div class="label">Active cases</div><div class="value" id="wCases">—</div></div><div class="metric"><div class="label">Watchlists</div><div class="value" id="wWatchlists">—</div></div><div class="metric"><div class="label">Saved searches</div><div class="value" id="wSearches">—</div></div><div class="metric"><div class="label">Watch alerts</div><div class="value" id="wAlerts">—</div></div></div></section>"""
        if role_has_permission(role, Permission.CLAIMS_VIEW)
        else ""
    )
    body = f"""
    <section class="page-head"><div><div class="eyebrow">Command center</div><h1>What’s changing in the news</h1><p class="lead">Start with developing events, compare new reports with earlier accounts and follow the evidence to the original source.</p><div class="small muted" style="margin-top:10px">Signed in as {_safe(user.verified_email or user.display_name or "approved user")} · {_safe(role_value.replace("_", " "))}</div></div><div class="toolbar"><span id="commandStatus" class="muted small" aria-live="polite">Loading workspace…</span><button class="secondary" id="refreshCommand" type="button">Refresh</button><a class="button ghost" href="/auth/logout">Log out</a></div></section>
    <section class="panel" style="margin-bottom:18px"><div class="section-head"><div><div class="eyebrow">Start here</div><h2>Your news in about two minutes</h2><p class="muted">Read the daily or weekly brief with original sources. Your reading period and personal feed are remembered.</p></div><a class="button" href="/briefs">Read my brief</a></div></section>
    <section class="grid four">
      <div class="metric"><div class="label">Developing events in view</div><div class="value" id="cEvents">—</div><div class="hint">Across loaded event window</div></div>
      <div class="metric"><div class="label">Reports in current sample</div><div class="value" id="cReports">—</div><div class="hint">Latest reporting window</div></div>
      <div class="metric"><div class="label">Material changes in sample</div><div class="value" id="cUpdates">—</div><div class="hint">Change signals from stored comparisons</div></div>
      <div class="metric"><div class="label">Conflict / revision signals</div><div class="value" id="cConflicts">—</div><div class="hint">Needs review · not proof of a contradiction</div></div>
    </section>
    <div class="notice command-scope" style="margin:14px auto 0;max-width:1520px"><b>About these counts:</b> the overview samples the latest 40 events and 100 reports. These are not all-time totals or independent-source counts.</div>
    <section class="grid two" style="margin-top:18px">
      <div class="panel"><div class="section-head"><div><h2>Developing events</h2><div class="muted small">Events with the most recent material activity.</div></div><a class="small" href="/events">View all events</a></div><div id="commandEvents" class="stack"><div class="skeleton" style="height:190px"></div></div></div>
      <div class="panel"><div class="section-head"><div><h2>Attention required</h2><div class="muted small">Reporting changes or extraction conditions worth reviewing.</div></div><a class="small" href="/news">Open news</a></div><div id="commandAttention" class="stack"><div class="skeleton" style="height:190px"></div></div></div>
    </section>
    {analyst_workspace_panel}
    <section style="margin-top:22px"><div class="section-head"><div><h2>Workspace</h2><div class="muted small">Quick routes into reporting, history, saved cases and source health.</div></div></div><div class="grid three">{''.join(quick_links)}</div></section>
    """
    scripts = f"""<script>{COMMON_JS}
function eventRow(e){{return `<a class="row-link" href="/events/${{niEsc(e.id)}}/intelligence"><div><b>${{niEsc(e.title)}}</b><div class="muted small" style="margin-top:4px">${{e.article_count||0}} reports · ${{e.publisher_count||0}} publishers · changed ${{niRelative(e.last_material_change_at)}}</div></div><span class="pill ${{['developing','active','open'].includes(String(e.lifecycle_status||'').toLowerCase())?'warn':'neutral'}}">${{niEsc(niTitle(e.lifecycle_status||'event'))}}</span></a>`}}
function attentionRow(a){{const conflict=a.historical_change_pattern==='possible_conflict_or_revision';const warnings=(a.latest_extraction_warnings||[]).length;const label=conflict?'Possible reporting conflict':a.historical_change_pattern==='material_update'?'Material update':warnings?'Extraction warning':'Review';const kind=conflict?'bad':'warn';return `<a class="row-link" href="/articles/${{niEsc(a.id)}}/intelligence"><div><b>${{niEsc(a.title)}}</b><div class="muted small" style="margin-top:4px">${{niDate(a.published_at||a.first_observed_at)}}${{warnings?` · ${{warnings}} extraction warning${{warnings===1?'':'s'}}`:''}}</div></div><span class="pill ${{kind}}">${{niEsc(label)}}</span></a>`}}
async function loadCommand(){{document.getElementById('refreshCommand').disabled=true;document.getElementById('commandStatus').textContent='Refreshing…';try{{const [events,articles]=await Promise.all([niApi('/api/v1/events?limit=40'),niApi('/api/v1/articles?limit=100')]);const developing=events.filter(e=>['developing','active','open'].includes(String(e.lifecycle_status||'').toLowerCase()));const updates=articles.filter(a=>a.historical_change_pattern==='material_update');const conflicts=articles.filter(a=>a.historical_change_pattern==='possible_conflict_or_revision');const warningArticles=articles.filter(a=>(a.latest_extraction_warnings||[]).length);document.getElementById('cEvents').textContent=developing.length;document.getElementById('cReports').textContent=articles.length;document.getElementById('cUpdates').textContent=updates.length;document.getElementById('cConflicts').textContent=conflicts.length;const eventRows=(developing.length?developing:events).slice(0,7);document.getElementById('commandEvents').innerHTML=eventRows.map(eventRow).join('')||'<div class="empty">No events are available yet.</div>';const attention=[...conflicts,...updates,...warningArticles].filter((a,i,arr)=>arr.findIndex(x=>x.id===a.id)===i).slice(0,8);document.getElementById('commandAttention').innerHTML=attention.map(attentionRow).join('')||'<div class="empty"><b>No immediate review signals.</b><div class="small" style="margin-top:5px">This means the loaded reporting window has no conflict, material-update or extraction-warning signals.</div></div>';document.getElementById('commandStatus').textContent=`Updated ${{new Date().toLocaleTimeString()}}`}}catch(err){{document.getElementById('commandStatus').textContent='Workspace data unavailable';document.getElementById('commandEvents').innerHTML=document.getElementById('commandAttention').innerHTML=`<div class="error-box">${{niEsc(err.message)}}</div>`}}finally{{document.getElementById('refreshCommand').disabled=false}}}}async function loadAnalystWorkspace(){{const caseNode=document.getElementById('wCases');if(!caseNode)return;try{{const w=await niOptional('/api/v1/workspace/overview');if(!w)return;document.getElementById('wCases').textContent=w.counts?.active_investigations||0;document.getElementById('wWatchlists').textContent=w.counts?.watchlists||0;document.getElementById('wSearches').textContent=w.counts?.saved_searches||0;document.getElementById('wAlerts').textContent=w.counts?.unacknowledged_alerts||0}}catch(err){{caseNode.textContent='—'}}}}
document.getElementById('refreshCommand').addEventListener('click',()=>{{loadCommand();loadAnalystWorkspace()}});loadCommand();loadAnalystWorkspace();
</script>"""
    extra_css = ".row-link{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;padding:12px;border:1px solid var(--line);border-radius:11px;text-decoration:none;background:var(--surface-2)}.row-link:hover{border-color:var(--line-strong);text-decoration:none}@media(max-width:620px){.row-link{flex-direction:column}}"
    return render_app_page(title="Command Center", body=body, active="workspace", role=role_value, scripts=scripts, extra_css=extra_css)


@router.get("/admin/access-console", response_class=HTMLResponse)
async def access_console(auth: AccessAdminAuth) -> str:
    body = """
    <section class="page-head"><div><div class="eyebrow">Administration</div><h1>User access</h1><p class="lead">Approve, reject, suspend, restore and revoke platform accounts.</p></div><button id="refreshAccess" type="button">Refresh</button></section>
    <section class="grid two">
      <div class="panel"><div class="section-head"><h2>Pending requests</h2><span id="pendingCount" class="pill neutral">0</span></div><div id="pendingList" class="stack"><div class="skeleton" style="height:120px"></div></div></div>
      <div class="panel"><div class="section-head"><h2>Users</h2></div><label>Search users<input id="userSearch" type="search" placeholder="Name or email" /></label><div id="userList" class="stack" style="margin-top:14px"><div class="skeleton" style="height:120px"></div></div></div>
    </section>
    <dialog id="accessActionDialog" aria-labelledby="accessDialogTitle">
      <div class="dialog-card" style="display:grid;gap:14px;min-width:min(440px,calc(100vw - 48px))">
        <div class="section-head"><h2 id="accessDialogTitle">Change account access</h2><button type="button" id="cancelAccessAction" class="ghost">Cancel</button></div>
        <p id="accessActionInfo" class="muted small"></p>
        <label id="accessRoleRow">Assign role<select id="accessActionRole"><option value="viewer">Viewer · read public reporting</option><option value="analyst">Analyst · investigate claims</option><option value="source_manager">Source manager · manage publishers</option><option value="administrator">Administrator · manage access</option></select></label>
        <label id="accessReasonRow">Reason for this change<textarea id="accessActionReason" maxlength="1000" placeholder="Explain the account action for the audit record"></textarea></label>
        <div id="accessActionError" class="small" role="alert" style="color:var(--bad)"></div>
        <button type="button" id="confirmAccessAction">Confirm change</button>
      </div>
    </dialog>
    """
    scripts = f"""<script>{COMMON_JS}
function userLine(user){{const label=`${{user.display_name||'Unnamed'}} · ${{user.verified_email||user.auth_provider_user_id}}`;return `<div class="row"><div><b>${{niEsc(label)}}</b><div class="pill-row" style="margin-top:6px">${{niPill(niTitle(user.access_status),user.access_status==='approved'?'good':'warn')}}${{niPill(niTitle(user.role),'neutral')}}</div></div><div class="toolbar"><button type="button" onclick="approve('${{user.id}}')">Approve</button><button class="secondary" type="button" onclick="suspendUser('${{user.id}}')">Suspend</button><button class="danger" type="button" onclick="revokeUser('${{user.id}}')">Revoke</button></div></div>`}}
async function loadAccess(){{try{{const pending=await niApi('/api/v1/admin/access/requests');document.getElementById('pendingCount').textContent=pending.length;document.getElementById('pendingList').innerHTML=pending.length?pending.map(x=>userLine(x.user)).join(''):'<div class="empty">No pending requests.</div>';await loadUsers()}}catch(e){{document.getElementById('pendingList').innerHTML=`<div class="error-box">${{niEsc(e.message)}}</div>`}}}}
async function loadUsers(){{const q=encodeURIComponent(document.getElementById('userSearch').value||'');try{{const users=await niApi(`/api/v1/admin/access/users${{q?'?q='+q:''}}`);document.getElementById('userList').innerHTML=users.length?users.map(userLine).join(''):'<div class="empty">No users match this search.</div>'}}catch(e){{document.getElementById('userList').innerHTML=`<div class="error-box">${{niEsc(e.message)}}</div>`}}}}
let pendingAccessAction=null;
function openAccessAction(action,id){{
 pendingAccessAction={{action,id}};
 const labels={{approve:'Approve account',suspend:'Suspend account',revoke:'Revoke account'}};
 document.getElementById('accessDialogTitle').textContent=labels[action];
 document.getElementById('accessActionInfo').textContent=action==='approve'?'Choose the minimum role this account needs.':action==='suspend'?'The account will lose access until restored.':'This account will lose access. Reversal requires an explicit new approval.';
 document.getElementById('accessRoleRow').hidden=action!=='approve';
 document.getElementById('accessReasonRow').hidden=action==='approve';
 document.getElementById('accessActionReason').value='';
 document.getElementById('accessActionError').textContent='';
 document.getElementById('confirmAccessAction').className=action==='revoke'?'danger':'';
 document.getElementById('accessActionDialog').showModal();
}}
function approve(id){{openAccessAction('approve',id)}}
function suspendUser(id){{openAccessAction('suspend',id)}}
function revokeUser(id){{openAccessAction('revoke',id)}}
async function confirmAccessAction(){{
 if(!pendingAccessAction)return;
 const {{action,id}}=pendingAccessAction, reason=document.getElementById('accessActionReason').value.trim(), btn=document.getElementById('confirmAccessAction');
 if(action!=='approve'&&reason.length<5){{document.getElementById('accessActionError').textContent='Enter a reason (at least 5 characters).';return}}
 const body=action==='approve'?{{role:document.getElementById('accessActionRole').value}}:{{reason,user_visible_reason:reason}};
 btn.disabled=true;
 try{{await niApi(`/api/v1/admin/access/users/${{id}}/${{action}}`,{{method:'POST',body:JSON.stringify(body)}});document.getElementById('accessActionDialog').close();pendingAccessAction=null;niToast(`Account ${{action}} action recorded`,'good');await loadAccess()}}
 catch(e){{document.getElementById('accessActionError').textContent=e.message}}
 finally{{btn.disabled=false}}
}}
document.getElementById('cancelAccessAction').addEventListener('click',()=>document.getElementById('accessActionDialog').close());
document.getElementById('confirmAccessAction').addEventListener('click',confirmAccessAction);
document.getElementById('refreshAccess').addEventListener('click',loadAccess);document.getElementById('userSearch').addEventListener('input',niDebounce(loadUsers,180));loadAccess();
</script>"""
    return render_app_page(title="Access Admin", body=body, active="admin", role=getattr(getattr(auth, "role", None), "value", "administrator"), scripts=scripts, extra_css=".row{display:flex;justify-content:space-between;gap:12px;align-items:center;border:1px solid var(--line);border-radius:12px;padding:12px}@media(max-width:700px){.row{align-items:stretch;flex-direction:column}}")


def _page(title: str, body: str) -> str:
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="light dark" />
  <title>{title} · News Intelligence</title>
  <style>
    {BASE_CSS}
    .public-main {{ width:min(1120px,calc(100% - 28px)); margin:auto; padding:48px 0 72px; }}
    .hero {{ min-height:58vh; display:grid; align-content:center; }} .hero h1,.toolbar-page h1,.narrow h1 {{ font-size:clamp(34px,6vw,62px); line-height:1; letter-spacing:-.04em; margin:6px 0 16px; }}
    .band,.grid {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px }}
    .tile {{ background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:20px;box-shadow:var(--shadow);text-decoration:none;transition:transform .15s ease,border-color .15s ease }} .tile:hover {{ transform:translateY(-2px);border-color:#bfcaf1;text-decoration:none }}
    .narrow {{ max-width:620px;margin:7vh auto }} .toolbar-page {{ display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:24px }}
    .row {{ display:flex;justify-content:space-between;gap:12px;align-items:center;border:1px solid var(--line);border-radius:12px;padding:12px }} .row p {{ margin:4px 0 0 }}
    .badge {{ display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:28px;border-radius:999px;background:var(--brand);color:#fff;font-size:14px }} .search {{ display:grid;gap:6px;margin-bottom:12px }}
    dl {{ display:grid;grid-template-columns:auto 1fr;gap:8px 14px }} dt {{ color:var(--muted) }} dd {{ margin:0;font-weight:700 }}
    @media(max-width:720px) {{ .toolbar-page,.row {{ align-items:stretch;flex-direction:column }} }}
  </style>
</head>
<body><main class="public-main">{body}</main></body>
</html>
"""


def _safe(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
