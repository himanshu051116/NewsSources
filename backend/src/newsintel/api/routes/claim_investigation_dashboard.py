# ruff: noqa: E501
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from newsintel.api.dependencies import AnalystAuth
from newsintel.api.ui import COMMON_JS, render_app_page
from newsintel.domain.access import Permission

router = APIRouter(tags=["claim-investigation-dashboard"])


@router.get("/claims/{claim_id}/investigation", response_class=HTMLResponse)
async def claim_investigation_dashboard(claim_id: UUID, auth: AnalystAuth) -> str:
    role = getattr(getattr(auth, "role", None), "value", "viewer")
    can_verify = Permission.CLAIMS_VERIFY.value in auth.permissions
    body = f"""
<section class="page-head">
  <div>
    <div class="eyebrow">Check a reported claim</div>
    <h1 id="claimTitle"><span class="skeleton" style="display:block;width:min(800px,82vw);height:46px"></span></h1>
    <div id="claimMeta" class="muted"></div>
  </div>
  <div class="toolbar"><a class="button ghost" href="/investigations?add_type=claim&add_id={claim_id}">Add to workspace</a><a id="articleLink" class="button secondary">Article</a><a id="eventLink" class="button ghost">Event dossier</a></div>
</section>
<section id="claimAlert" aria-live="polite"></section>
<section class="grid four" id="claimMetrics">
  <div class="metric"><div class="label">Verification</div><div class="value" id="mVerification">—</div></div>
  <div class="metric"><div class="label">Evidence links</div><div class="value" id="mLinks">—</div></div>
  <div class="metric"><div class="label">Distinct source chains</div><div class="value" id="mLineages">—</div><div class="hint">Repeated reporting counted once per recorded chain</div></div>
  <div class="metric"><div class="label">Primary evidence</div><div class="value" id="mPrimary">—</div></div>
</section>
<section class="panel" style="margin-top:18px;padding-bottom:0">
  <div class="tabs" role="tablist" aria-label="Claim investigation sections">
    <button class="tab active" data-tab="overview" type="button" role="tab" aria-selected="true">Overview</button>
    <button class="tab" data-tab="evidence" type="button" role="tab" aria-selected="false">Evidence</button>
    <button class="tab" data-tab="lineages" type="button" role="tab" aria-selected="false">Lineages</button>
    <button class="tab" data-tab="history" type="button" role="tab" aria-selected="false">Decision history</button>
  </div>
  <div id="tab-overview" class="tab-panel active">
    <div class="grid two">
      <section><div class="section-head"><h2>Current assessment</h2></div><div id="assessment"><div class="skeleton" style="height:180px"></div></div></section>
      <section><div class="section-head"><h2>Evidence search</h2></div><div id="searchState"><div class="skeleton" style="height:180px"></div></div></section>
    </div>
    <section style="margin-top:22px"><div class="section-head"><h2>Review state</h2></div><div id="reviewFlags"></div></section>
    <section style="margin-top:22px"><div class="section-head"><h2>Analyst actions</h2><span class="muted small">Actions create auditable backend records; they do not silently rewrite evidence.</span></div><div id="analystActions" class="toolbar"></div></section>
  </div>
  <div id="tab-evidence" class="tab-panel"><div class="section-head"><div><h2>Evidence links</h2><div class="muted small">Raw linked evidence. Multiple links may belong to one lineage.</div></div></div><div id="evidenceList" class="stack"><div class="skeleton" style="height:180px"></div></div></div>
  <div id="tab-lineages" class="tab-panel"><div class="section-head"><div><h2>Where the evidence came from</h2><div class="muted small">Repeated links to the same reporting chain are grouped. Shared ownership and circular sourcing may reduce independence but do not prove a report is wrong.</div></div></div><div id="lineageList" class="stack"><div class="skeleton" style="height:180px"></div></div></div>
  <div id="tab-history" class="tab-panel"><div class="section-head"><div><h2>Verification history</h2><div class="muted small">Stored decision revisions and methodology versions.</div></div></div><div id="verificationHistory" class="timeline"><div class="skeleton" style="height:180px"></div></div></div>
</section>
"""
    claim_id_text = str(claim_id)
    can_verify_js = "true" if can_verify else "false"
    scripts = f"""<script>{COMMON_JS}
const claimId={claim_id_text!r};const canVerify={can_verify_js};let dossier=null;
niInitTabs();
function verdictKind(v){{const x=String(v||'').toLowerCase();if(x==='supported')return 'good';if(['contradicted','misleading'].includes(x))return 'bad';if(['disputed','unsupported','not_checkable','insufficient_evidence'].includes(x))return 'warn';return 'neutral'}}
function relationshipKind(v){{const x=String(v||'').toLowerCase();if(['support','supports','supported','corroborates'].includes(x))return 'good';if(['contradict','contradicts','contradicted'].includes(x))return 'bad';if(['dispute','disputed'].includes(x))return 'warn';return 'neutral'}}
function lineageKeyLabel(v){{if(!v)return 'Unidentified lineage';const parts=String(v).split(':');return parts.length>1?`${{niTitle(parts[0])}} · ${{parts.slice(1).join(':')}}`:v}}
function evidenceFlags(e){{const m=e.metadata||{{}};let flags=[];if(m.primary_source||m.primary_source_validated_by_registry)flags.push(niPill('Primary','good'));if(m.shared_ownership_group)flags.push(niPill('Shared ownership','warn'));if(m.circular_sourcing_detected)flags.push(niPill('Circular sourcing','warn'));if(typeof m.max_prior_lineage_similarity==='number'&&m.max_prior_lineage_similarity>=.70)flags.push(niPill(`Near-duplicate ${{Math.round(m.max_prior_lineage_similarity*100)}}%`,'warn'));if(typeof e.independence_score==='number')flags.push(niPill(`Independence ${{Math.round(e.independence_score*100)}}%`,'neutral'));return flags.join('')}}
function render(){{const c=dossier.claim;const v=c.latest_verification;document.getElementById('claimTitle').textContent=c.claim_text;document.title=`Claim investigation · News Intelligence`;document.getElementById('claimMeta').textContent=`${{dossier.publisher_name}} · ${{dossier.article_title}}`;document.getElementById('articleLink').href=`/articles/${{c.article_id}}/intelligence`;document.getElementById('eventLink').href=`/events/${{dossier.event_id}}/intelligence`;document.getElementById('mVerification').textContent=niTitle(v?.label||'unverified');document.getElementById('mLinks').textContent=(c.evidence_links||[]).length;document.getElementById('mLineages').textContent=(dossier.lineages||[]).length;document.getElementById('mPrimary').textContent=(c.evidence_links||[]).filter(e=>e.metadata?.primary_source||e.metadata?.primary_source_validated_by_registry).length;renderOverview();renderEvidence();renderLineages();renderHistory()}}
function renderOverview(){{const c=dossier.claim;const v=c.latest_verification;const conflict=dossier.latest_conflict;document.getElementById('assessment').innerHTML=`<div class="pill-row">${{niPill(niTitle(v?.label||'unverified'),verdictKind(v?.label))}}${{c.extraction_features?.claim_type?niPill(niTitle(c.extraction_features.claim_type),'neutral'):''}}</div><p style="margin:14px 0 0"><b>${{niEsc(c.claim_text)}}</b></p>${{v?`<div class="muted small" style="margin-top:10px">Methodology ${{niEsc(v.methodology_version)}} · stored ${{niDate(v.created_at)}}</div>${{v.reasoning_trace?.conclusion?`<div class="notice" style="margin-top:12px">${{niEsc(v.reasoning_trace.conclusion)}}</div>`:''}}`:'<div class="notice warn" style="margin-top:12px">No verification decision has been stored yet.</div>'}}${{conflict?`<div class="notice ${{['resolved_support','resolved_contradiction'].includes(conflict.state)?'':'warn'}}" style="margin-top:12px"><b>Conflict state: ${{niEsc(niTitle(conflict.state))}}</b><div class="small" style="margin-top:5px">Support ${{conflict.support_weight.toFixed(2)}} · contradiction ${{conflict.contradiction_weight.toFixed(2)}} · dispute ${{conflict.dispute_weight.toFixed(2)}} · ${{conflict.independent_lineage_count}} lineages</div></div>`:''}}`;
const run=dossier.latest_search_run;document.getElementById('searchState').innerHTML=run?`<div class="grid two"><div class="metric"><div class="label">Status</div><div class="value">${{niEsc(niTitle(run.status))}}</div></div><div class="metric"><div class="label">Retrieval complete</div><div class="value">${{run.retrieval_complete?'Yes':'No'}}</div></div><div class="metric"><div class="label">Sources</div><div class="value">${{run.source_count}}</div></div><div class="metric"><div class="label">Evidence records</div><div class="value">${{run.evidence_count}}</div></div></div><div class="muted small" style="margin-top:10px">Planner ${{niEsc(run.planner_version)}} · started ${{niDate(run.started_at)}}</div>`:'<div class="empty">No evidence-search run has been recorded for this claim.</div>';
const flags=dossier.review_flags||[];document.getElementById('reviewFlags').innerHTML=flags.length?flags.map(f=>`<div class="notice ${{f.state==='review_required'?'warn':''}}" style="margin-bottom:8px"><div class="pill-row">${{niPill(niTitle(f.severity),f.severity==='critical'?'bad':'warn')}}${{niPill(niTitle(f.state),'neutral')}}</div><div style="margin-top:7px">${{niEsc(f.reason)}}</div>${{(f.actions||[]).length?`<div class="muted small" style="margin-top:5px">Suggested: ${{f.actions.map(niTitle).join(' · ')}}</div>`:''}}</div>`).join(''):'<div class="empty">No correction/retraction review flags are attached.</div>';
const actions=document.getElementById('analystActions');actions.innerHTML=canVerify?`<button id="createPlan" class="secondary" type="button">Create evidence plan</button><button id="resolveConflict" class="secondary" type="button">Reassess conflict</button><button id="reverify" type="button">Recompute verification</button>`:'<div class="notice">Your account can inspect this claim but cannot create verification decisions.</div>';if(canVerify)wireActions()}}
function renderEvidence(){{const rows=dossier.claim.evidence_links||[];document.getElementById('evidenceList').innerHTML=rows.length?rows.map(e=>`<div class="evidence-item"><div class="pill-row">${{niPill(niTitle(e.relationship||'context'),relationshipKind(e.relationship))}}${{niPill(niTitle(e.source_type||'source'),'neutral')}}${{evidenceFlags(e)}}</div><div style="margin-top:8px"><a href="${{niEsc(niSafeUrl(e.source_url))}}" target="_blank" rel="noopener noreferrer">${{niEsc(e.source_url)}}</a></div>${{e.metadata?.lineage_key?`<div class="muted small" style="margin-top:6px">Lineage: ${{niEsc(lineageKeyLabel(e.metadata.lineage_key))}}</div>`:''}}${{e.metadata?.passage_text?`<div class="prose" style="font-size:13px;margin-top:8px">${{niEsc(e.metadata.passage_text)}}</div>`:''}}</div>`).join(''):'<div class="empty">No evidence links are attached yet.</div>'}}
function renderLineages(){{const rows=dossier.lineages||[];document.getElementById('lineageList').innerHTML=rows.length?rows.map(l=>`<div class="evidence-item"><div class="section-head" style="margin:0"><div><b>${{niEsc(lineageKeyLabel(l.lineage_key))}}</b><div class="muted small">${{l.link_count}} links · ${{l.source_count}} source URL${{l.source_count===1?'':'s'}} · max independence ${{Math.round(l.max_independence_score*100)}}%</div></div><div class="pill-row">${{l.primary_source_present?niPill('Primary','good'):''}}${{l.shared_ownership_present?niPill('Shared ownership','warn'):''}}${{l.circular_sourcing_present?niPill('Circular sourcing','warn'):''}}</div></div><div class="pill-row" style="margin-top:8px">${{(l.relationships||[]).map(r=>niPill(niTitle(r),relationshipKind(r))).join('')}}</div>${{(l.source_urls||[]).length?`<div class="small" style="margin-top:8px">${{l.source_urls.map(u=>`<div><a href="${{niEsc(niSafeUrl(u))}}" target="_blank" rel="noopener noreferrer">${{niEsc(u)}}</a></div>`).join('')}}</div>`:''}}</div>`).join(''):'<div class="empty">No evidence lineages have been identified yet.</div>'}}
function renderHistory(){{const rows=dossier.verification_history||[];document.getElementById('verificationHistory').innerHTML=rows.length?rows.map(v=>`<div class="timeline-item"><div class="pill-row">${{niPill(niTitle(v.label),verdictKind(v.label))}}${{v.confidence_score!=null?niPill(`Stored confidence ${{Math.round(v.confidence_score*100)}}%`,'neutral'):''}}</div><div style="margin-top:6px">${{niEsc(v.reasoning_trace?.conclusion||'Stored verification revision')}}</div><div class="timeline-time">${{niDate(v.created_at)}} · ${{niEsc(v.methodology_version)}}</div></div>`).join(''):'<div class="empty">No verification history has been stored.</div>'}}
async function post(path,body){{const options={{method:'POST'}};if(body!==undefined)options.body=JSON.stringify(body);return niApi(path,options)}}
function wireActions(){{document.getElementById('createPlan').addEventListener('click',async e=>{{e.currentTarget.disabled=true;try{{const r=await post(`/api/v1/claims/${{claimId}}/evidence-plan`);niToast(`Evidence plan created · ${{r.run?.status||'planned'}}`,'good');await load()}}catch(err){{niToast(err.message,'bad')}}finally{{e.currentTarget.disabled=false}}}});document.getElementById('resolveConflict').addEventListener('click',async e=>{{e.currentTarget.disabled=true;try{{await post(`/api/v1/claims/${{claimId}}/conflict-resolution`);niToast('Conflict assessment updated','good');await load()}}catch(err){{niToast(err.message,'bad')}}finally{{e.currentTarget.disabled=false}}}});document.getElementById('reverify').addEventListener('click',async e=>{{e.currentTarget.disabled=true;try{{const complete=Boolean(dossier.latest_search_run?.retrieval_complete);await post(`/api/v1/claims/${{claimId}}/verify`,{{retrieval_complete:complete}});niToast('Verification recomputed','good');await load()}}catch(err){{niToast(err.message,'bad')}}finally{{e.currentTarget.disabled=false}}}})}}
async function load(){{try{{dossier=await niApi(`/api/v1/claims/${{claimId}}/dossier`);render()}}catch(err){{document.getElementById('claimTitle').textContent='Unable to load claim';document.getElementById('claimAlert').innerHTML=`<div class="error-box">${{niEsc(err.message)}}</div>`}}}}
load();
</script>"""
    return render_app_page(title="Claim Investigation", body=body, active="events", role=role, scripts=scripts)
