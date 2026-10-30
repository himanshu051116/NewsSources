# ruff: noqa: E501
"""Readable, source-cited event briefing. Presentation never fabricates missing support."""
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from newsintel.api.dependencies import AnalystAuth
from newsintel.api.ui import COMMON_JS, render_app_page

router = APIRouter(tags=["briefing-dashboard"])


@router.get("/events/{event_id}/briefing", response_class=HTMLResponse)
async def event_briefing_dashboard(event_id: UUID, auth: AnalystAuth) -> str:
    role = getattr(getattr(auth, "role", None), "value", "viewer")
    body = f"""
<section class="briefing-hero">
  <div><a class="briefing-back" href="/events/{event_id}/intelligence">← Back to event</a>
  <p class="eyebrow" style="margin-top:16px">Event briefing · Based on recorded sources</p>
  <h1 id="title">Loading event briefing…</h1>
  <p class="lead" id="briefingSubhead">The latest reporting, earlier context and what remains uncertain.</p>
  <div class="briefing-meta" id="meta" aria-live="polite"></div></div>
  <a class="button secondary" href="/events/{event_id}/intelligence">View full event record</a>
</section>
<div id="status" role="status" aria-live="polite"></div>
<div class="briefing-summary-grid">
  <section class="panel briefing-primary"><div class="eyebrow">Overview</div><h2>What happened</h2><div id="whatHappened" class="briefing-statement"></div>
    <div class="briefing-subsection"><h3>Latest reporting</h3><div id="latestReporting" class="stack"></div></div></section>
  <section class="panel briefing-context"><div class="eyebrow">In perspective</div><h2>What changed</h2><div id="whatChanged" class="briefing-statement"></div>
    <div class="briefing-subsection"><h3>Impact and significance</h3><div id="whyMatters" class="briefing-statement"></div><p class="small muted">Contextual analysis is separate from established facts. Check the cited material.</p></div></section>
</div>
<section class="panel briefing-section"><div class="section-head"><div><div class="eyebrow">Before this development</div><h2>Historical context</h2><p class="muted small">Earlier dated reporting linked to this event—not independent proof of today's claims.</p></div></div><div id="history" class="timeline"></div></section>
<section class="briefing-findings"><section class="panel"><div class="section-head"><h2><span class="finding-icon verified">✓</span> Evidence supports</h2></div><div id="established" class="stack"></div></section>
  <section class="panel"><div class="section-head"><h2><span class="finding-icon disputed">!</span> Disputed reports</h2></div><div id="disputed" class="stack"></div></section>
  <section class="panel"><div class="section-head"><h2><span class="finding-icon unresolved">?</span> Still unresolved</h2></div><div id="unresolved" class="stack"></div></section></section>
<section class="panel briefing-section"><div class="section-head"><h2>Corrections and retractions</h2><span class="small muted">Confirmed records only</span></div><div id="corrections" class="stack"></div></section>
<section class="panel briefing-section" id="evidenceSection"><div class="section-head"><div><div class="eyebrow">Trace every statement</div><h2>Sources and references</h2><p class="muted small">Reference numbers link to the records used in this briefing.</p></div><span id="refCount" class="pill neutral"></span></div><div id="refs" class="evidence-reference-grid"></div>
<details class="method-details"><summary>How this briefing was assembled</summary><div id="method" class="notice" style="margin-top:12px"></div></details></section>
"""
    extra_css = """
.briefing-hero{display:flex;justify-content:space-between;align-items:flex-end;gap:26px;border-bottom:1px solid var(--line);padding:8px 0 27px;margin-bottom:22px}.briefing-hero h1{font-size:clamp(29px,3.6vw,47px);letter-spacing:-.04em;line-height:1.15;margin:8px 0 6px;max-width:980px}.briefing-back{font-weight:700;font-size:12px}.briefing-meta{font-size:12px;color:var(--muted);margin-top:15px}.briefing-summary-grid{display:grid;grid-template-columns:1.24fr 1fr;gap:16px;margin:18px 0}.briefing-primary,.briefing-context{min-height:270px}.briefing-primary h2,.briefing-context h2{font-size:22px;letter-spacing:-.025em;margin:8px 0 16px}.briefing-subsection{border-top:1px solid var(--line);margin-top:20px;padding-top:15px}.briefing-subsection h3{margin:0 0 12px;font-size:14px}.briefing-statement p{font-size:15px;line-height:1.8;margin:0 0 10px}.briefing-section{margin-top:17px}.briefing-findings{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:17px}.briefing-findings .panel{min-width:0}.briefing-findings h2{display:flex;align-items:center;gap:9px}.finding-icon{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:13px}.verified{color:var(--good);background:var(--good-bg)}.disputed{color:var(--bad);background:var(--bad-bg)}.unresolved{color:var(--warn);background:var(--warn-bg)}.briefing-refs{display:flex;gap:6px;flex-wrap:wrap;margin:9px 0 5px}.source-ref{font-size:11px;font-weight:800;color:#194eaf;background:#eef3ff;padding:4px 8px;border-radius:6px;border:1px solid #d8e5ff}.source-ref:hover{background:#dbe8ff;text-decoration:none}.source-ref-missing{font-size:11px;color:var(--bad)}.briefing-item{border:1px solid var(--line);background:#fbfcff;border-radius:10px;padding:12px 13px}.briefing-item b{font-size:13px;line-height:1.5}.briefing-item .small{margin-top:5px}.evidence-reference-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.reference-card{scroll-margin-top:85px;border:1px solid var(--line);border-radius:11px;padding:13px;background:#f9fbff}.reference-card:target{outline:2px solid var(--brand)}.reference-card .source-no{color:var(--brand);font-size:12px;font-weight:850}.reference-card .source-title{font-weight:750;margin:4px 0 5px;overflow-wrap:anywhere}.reference-card .source-id{font-size:10px;overflow-wrap:anywhere;color:var(--muted)}.method-details{margin-top:18px;border-top:1px solid var(--line);padding-top:15px}.method-details summary{font-weight:750;cursor:pointer}.briefing-section .timeline-item{padding-bottom:21px}.briefing-section .timeline-item b{font-size:14px}@media(max-width:1050px){.briefing-findings{grid-template-columns:1fr}.briefing-summary-grid{grid-template-columns:1fr}}@media(max-width:720px){.briefing-hero{flex-direction:column;align-items:flex-start}.evidence-reference-grid{grid-template-columns:1fr}}
"""
    scripts = "<script>" + COMMON_JS + r"""
const eventId = __EVENT_ID__;
let knownReferences = new Map();
function references(ids){
 const values=[...new Set(ids||[])];
 if(!values.length)return '<span class="small muted">No linked reference</span>';
 const badges=values.slice(0,8).map(id=>{
   const r=knownReferences.get(String(id));
   if(!r)return `<span class="source-ref-missing" title="Reference not available in this snapshot">Reference unavailable</span>`;
   return `<a class="source-ref" href="#source-reference-${r.index}" title="${niEsc(r.title||r.kind||'Stored source')}" aria-label="See source ${r.index}">[${r.index}]</a>`;
 });
 if(values.length>8)badges.push(`<span class="small muted">+${values.length-8} more</span>`);
 return `<div class="briefing-refs">${badges.join('')}</div>`;
}
function statement(item){return item&&item.text ? `<div><p>${niEsc(item.text)}</p>${references(item.evidence_ids)}</div>`:'<div class="empty">Not enough recorded evidence for this section.</div>';}
function claimList(rows,empty){return (rows||[]).map(x=>`<article class="briefing-item"><b>${niEsc(x.text||'')}</b><div class="muted small">${niEsc(niTitle(x.verification||'unverified'))} · ${Number(x.evidence_link_count)||0} linked evidence records</div>${x.evidence_trace_warning?`<div class="notice warn small" style="margin-top:7px">${niEsc(x.evidence_trace_warning)}</div>`:''}${references(x.evidence_ids)}</article>`).join('')||`<div class="empty">${niEsc(empty)}</div>`;}
function renderSources(refs){
 knownReferences=new Map(refs.map((r,i)=>[String(r.id),{...r,index:i+1}]));
 document.getElementById('refCount').textContent=`${refs.length} references`;
 document.getElementById('refs').innerHTML=refs.map((r,i)=>`<article class="reference-card" id="source-reference-${i+1}"><div class="source-no">SOURCE ${i+1}</div><div class="source-title">${niEsc(r.title||niTitle(r.kind||'Stored record'))}</div><div class="muted small">${niEsc(niTitle(r.kind||'record'))}</div>${r.url?`<a href="${niEsc(niSafeUrl(r.url))}" target="_blank" rel="noopener noreferrer">Open original ↗</a>`:''}<details style="margin-top:7px"><summary class="small">Record identifier</summary><div class="source-id">${niEsc(r.id)}</div></details></article>`).join('')||'<div class="empty">No references recorded for this briefing.</div>';
}
async function load(){
 try{
   const data=await niApi(`/api/v1/events/${eventId}/briefing`), p=data.payload||{};
   renderSources(data.evidence_refs||[]);
   document.getElementById('title').textContent=p.event?.title||'Event briefing';
   document.title=`${p.event?.title||'Event'} · Briefing`;
   document.getElementById('meta').textContent=`Briefing snapshot ${niDate(data.generated_at)} · Event: ${niTitle(p.event?.lifecycle_status||'Unknown')}`;
   document.getElementById('status').innerHTML='<div class="notice"><b>About this briefing:</b> It uses stored reports, historical records and claim assessments. A cited report is not automatically an independently verified fact; gaps remain visible.</div>';
   document.getElementById('whatHappened').innerHTML=statement(p.what_happened);
   document.getElementById('latestReporting').innerHTML=(p.latest_reporting||[]).map(x=>`<article class="briefing-item"><b>${niEsc(x.title||x.text||'Untitled report')}</b><div class="muted small">${niEsc(x.publisher||'Publisher not recorded')} · ${niDate(x.published_at)}</div>${references(x.evidence_ids)}</article>`).join('')||'<div class="empty">No current reports were available in this snapshot.</div>';
   document.getElementById('whatChanged').innerHTML=statement(p.what_changed);
   document.getElementById('whyMatters').innerHTML=statement(p.why_it_matters);
   document.getElementById('history').innerHTML=(p.historical_background||[]).map(x=>`<article class="timeline-item"><b>${niEsc(x.title||'Earlier report')}</b><div class="muted small">${niEsc(x.source||'Source not recorded')} · ${x.date_basis==='observation'?'Observed':x.date_basis==='unknown'?'Date unverified':'Published'}: ${x.published_at||x.observed_at?niDate(x.published_at||x.observed_at):'Not recorded'}</div>${x.url?`<a class="small" href="${niEsc(niSafeUrl(x.url))}" target="_blank" rel="noopener noreferrer">Open original ↗</a>`:''}${references(x.ref?[x.ref]:[])}</article>`).join('')||'<div class="empty">No earlier reporting is linked in this snapshot.</div>';
   document.getElementById('established').innerHTML=claimList(p.established_facts,'No current claim has a recorded supporting verification decision.');
   document.getElementById('disputed').innerHTML=claimList(p.disputed_or_contradicted,'No disputed or contradicted claims are listed. This does not prove that there is no disagreement.');
   document.getElementById('unresolved').innerHTML=claimList(p.unresolved_or_insufficient_evidence,'No unresolved claims are listed for this snapshot.');
   document.getElementById('corrections').innerHTML=(p.corrections||[]).map(x=>`<article class="briefing-item">${niPill(niTitle(x.kind),'warn')}<div style="margin-top:8px">${niEsc(x.note||'Confirmed correction record')}</div><div class="muted small">${niDate(x.created_at)}</div></article>`).join('')||'<div class="empty">No confirmed corrections are attached to this event.</div>';
   const method=document.getElementById('method');method.replaceChildren();
   const strong=document.createElement('strong');strong.textContent=data.methodology_version||'Methodology';
   const rule=document.createElement('p');rule.textContent=p.methodology?.grounding_rule||'This briefing is assembled from stored, cited records; it does not independently verify every source claim.';
   const hash=document.createElement('code');hash.textContent=`Evidence snapshot SHA-256: ${data.evidence_pack_sha256||'unavailable'}`;
   method.append(strong,rule,hash);
 }catch(err){
   document.getElementById('title').textContent='Briefing unavailable';
   document.getElementById('status').innerHTML=`<div class="notice warn"><b>Briefing not available.</b> ${niEsc(err.message)}. The history and briefing workers may still be processing this event.</div>`;
 }
}
load();
""".replace("__EVENT_ID__", repr(str(event_id))) + "</script>"
    return render_app_page(title="Event briefing", body=body, active="events", role=role, scripts=scripts, extra_css=extra_css)
