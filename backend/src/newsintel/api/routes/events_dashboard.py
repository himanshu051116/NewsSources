# ruff: noqa: E501
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from newsintel.api.dependencies import ViewerAuth
from newsintel.api.ui import COMMON_JS, render_app_page

router = APIRouter(tags=["events-dashboard"])


@router.get("/events", response_class=HTMLResponse)
async def events_dashboard(auth: ViewerAuth) -> str:
    role = getattr(getattr(auth, "role", None), "value", "viewer")
    body = r"""
<section class="page-head">
  <div>
    <div class="eyebrow">Follow events</div>
    <h1>Events</h1>
    <p class="lead">See all reporting connected to the same event, follow its timeline and compare what different publishers have said.</p>
  </div>
  <div class="toolbar"><span id="eventsStatus" class="muted small" aria-live="polite">Loading events…</span><button class="secondary" id="refreshEvents" type="button">Refresh</button></div>
</section>
<section class="grid four" id="eventMetrics">
  <div class="metric"><div class="label">Loaded events</div><div class="value" id="mEvents">—</div></div>
  <div class="metric"><div class="label">Developing</div><div class="value" id="mDeveloping">—</div></div>
  <div class="metric"><div class="label">Reports linked to these events</div><div class="value" id="mReports">—</div></div>
  <div class="metric"><div class="label">Publisher appearances</div><div class="value" id="mPublishers">—</div><div class="hint">Per-event publisher counts added together; not unique outlets</div></div>
</section>
<section class="panel flat stack" style="margin-top:18px" aria-label="Event filters">
  <div class="toolbar grow">
    <label class="sr-only" for="eventSearch">Search events</label>
    <input id="eventSearch" type="search" autocomplete="off" placeholder="Search event title…" />
    <select id="lifecycleFilter" aria-label="Filter by lifecycle">
      <option value="">All lifecycle states</option>
      <option value="developing">Developing</option>
      <option value="active">Active</option>
      <option value="stable">Stable</option>
      <option value="closed">Closed</option>
    </select>
  </div>
</section>
<section style="margin-top:18px">
  <div class="section-head"><h2>Events in the archive</h2><span id="eventCount" class="muted small"></span></div>
  <div id="eventList" class="article-list" aria-live="polite"><div class="skeleton" style="height:180px"></div></div>
  <div class="toolbar" style="justify-content:center;margin-top:16px"><button id="loadMoreEvents" class="secondary" type="button">Load more events</button></div>
</section>
"""
    scripts = f"""<script>{COMMON_JS}
let events=[];let nextOffset=0;let reachedEnd=false;const pageSize=100;
const eventList=document.getElementById('eventList');
function lifecycleKind(v){{const value=String(v||'').toLowerCase();if(['closed','stable','resolved'].includes(value))return 'good';if(['developing','active','open'].includes(value))return 'warn';return 'neutral'}}
function updateMetrics(){{document.getElementById('mEvents').textContent=events.length;document.getElementById('mDeveloping').textContent=events.filter(e=>['developing','active','open'].includes(String(e.lifecycle_status||'').toLowerCase())).length;document.getElementById('mReports').textContent=events.reduce((n,e)=>n+(e.article_count||0),0);document.getElementById('mPublishers').textContent=events.reduce((n,e)=>n+(e.publisher_count||0),0)}}
function renderEvents(){{updateMetrics();document.getElementById('eventCount').textContent=`${{events.length}} loaded events`;if(!events.length){{eventList.innerHTML='<div class="empty"><b>No events match this view.</b><div class="small" style="margin-top:6px">Try a broader title search or clear the lifecycle filter.</div></div>';return}}eventList.innerHTML=events.map(e=>`<article class="story-card"><div><div class="pill-row">${{niPill(niTitle(e.lifecycle_status||'unknown'),lifecycleKind(e.lifecycle_status))}}${{niPill(niTitle(e.assignment_status||'unknown'),'neutral')}}</div><h2><a href="/events/${{niEsc(e.id)}}/intelligence">${{niEsc(e.title)}}</a></h2><div class="muted small">First detected ${{niDate(e.first_detected_at)}} · last material change ${{niRelative(e.last_material_change_at)}}</div><div class="pill-row" style="margin-top:10px">${{niPill(`${{e.article_count||0}} linked reports`,'neutral')}}${{niPill(`${{e.publisher_count||0}} publishers`,'neutral')}}</div></div><div class="story-side"><div class="pattern">${{niEsc(niTitle(e.lifecycle_status||'event'))}}</div><div class="muted small" style="margin-top:5px">${{niDate(e.last_material_change_at)}}</div><div style="margin-top:14px"><a class="button secondary" href="/events/${{niEsc(e.id)}}/intelligence">Open dossier</a></div></div></article>`).join('')}}
async function loadEvents({{append=false}}={{}}){{const refresh=document.getElementById('refreshEvents'),more=document.getElementById('loadMoreEvents');if(!append)refresh.disabled=true;else more.disabled=true;const query=document.getElementById('eventSearch').value.trim();const lifecycle=document.getElementById('lifecycleFilter').value;const offset=append?nextOffset:0;const params=new URLSearchParams({{limit:String(pageSize),offset:String(offset)}});if(query)params.set('query',query);if(lifecycle)params.set('lifecycle_status',lifecycle);try{{const data=await niApi(`/api/v1/events?${{params.toString()}}`);if(append){{const known=new Set(events.map(e=>e.id));for(const e of data)if(!known.has(e.id))events.push(e)}}else events=data;nextOffset=events.length;reachedEnd=data.length<pageSize;more.hidden=reachedEnd;document.getElementById('eventsStatus').textContent=`Updated ${{new Date().toLocaleTimeString()}}`;renderEvents()}}catch(e){{if(!append)eventList.innerHTML=`<div class="error-box"><b>Could not load events.</b><div class="small" style="margin-top:5px">${{niEsc(e.message)}}</div></div>`;else niToast(e.message,'bad');document.getElementById('eventsStatus').textContent='Events unavailable'}}finally{{refresh.disabled=false;more.disabled=false}}}}
const reload=niDebounce(()=>loadEvents(),220);document.getElementById('eventSearch').addEventListener('input',reload);document.getElementById('lifecycleFilter').addEventListener('change',()=>loadEvents());document.getElementById('refreshEvents').addEventListener('click',()=>loadEvents());document.getElementById('loadMoreEvents').addEventListener('click',()=>loadEvents({{append:true}}));loadEvents();
</script>"""
    return render_app_page(title="Events", body=body, active="events", role=role, scripts=scripts)
