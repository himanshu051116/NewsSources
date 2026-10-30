# ruff: noqa: E501
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from newsintel.api.dependencies import AnalystAuth
from newsintel.api.ui import COMMON_JS, render_app_page
from newsintel.domain.access import Permission

router = APIRouter(tags=["search-quality-dashboard"])


@router.get("/search-quality", response_class=HTMLResponse)
async def search_quality_dashboard(auth: AnalystAuth) -> str:
    role = getattr(getattr(auth, "role", None), "value", "analyst")
    can_manage = Permission.CLAIMS_VERIFY.value in auth.permissions
    hidden = "" if can_manage else "hidden"
    body = f"""
<section class="page-head"><div><div class="eyebrow">Measured retrieval quality</div><h1>Search Quality</h1><p class="lead">Evaluate ranked retrieval on labelled queries before introducing semantic reranking. Metrics are only meaningful when relevance-judgment coverage is adequate.</p></div><div class="toolbar"><a class="button secondary" href="/search">Open search</a><button id="exportBenchmark" class="secondary" type="button">Export JSON</button><button id="importBenchmark" class="secondary" type="button" {hidden}>Import JSON</button></div></section>
<section class="panel flat stack"><div class="toolbar grow"><label>Benchmark set<input id="benchmarkSet" value="local-search-v1" maxlength="120"/></label><label>Evaluation mode<select id="evaluationMode"><option value="lexical">Production lexical baseline</option><option value="hybrid_article_rerank">Hybrid article rerank experiment</option></select></label><button id="loadBenchmark" class="secondary" type="button">Load</button><button id="evaluateBenchmark" type="button" {hidden}>Evaluate</button></div><div class="notice">Unjudged returned results are treated as non-relevant by NDCG/MRR/Recall calculations. Hybrid reranking is experiment-only, requires article-only benchmark queries, and never changes production search automatically.</div><div id="experimentStatus" class="muted small">Loading experiment status…</div></section>
<section class="grid four" style="margin-top:18px"><div class="metric"><div class="label">24h search observations</div><div id="qObs" class="value">—</div></div><div class="metric"><div class="label">p50 latency</div><div id="qP50" class="value">—</div></div><div class="metric"><div class="label">p95 latency</div><div id="qP95" class="value">—</div></div><div class="metric"><div class="label">Slow &gt; 1.5s</div><div id="qSlow" class="value">—</div></div></section>
<section class="grid two" style="margin-top:18px"><div class="panel flat"><div class="section-head"><div><h2>Promotion gate</h2><div class="muted small">Human release gate; PASS never enables reranking automatically.</div></div><div class="toolbar"><button id="editPromotionPolicy" class="secondary" type="button" {hidden}>Policy</button><button id="evaluatePromotion" type="button" {hidden}>Evaluate gate</button></div></div><div id="promotionBox"><div class="empty">Load a benchmark set.</div></div><div id="promotionHistory" class="stack" style="margin-top:10px"></div></div><div class="panel flat"><div class="section-head"><div><h2>Semantic index coverage</h2><div class="muted small">Current article versions only; stale hashes/models do not count as fresh.</div></div><button id="reloadSemantic" class="secondary" type="button">Reload</button></div><div class="grid four compact-grid"><div class="metric"><div class="label">Current</div><div id="sCurrent" class="value">—</div></div><div class="metric"><div class="label">Fresh</div><div id="sFresh" class="value">—</div></div><div class="metric"><div class="label">Missing</div><div id="sMissing" class="value">—</div></div><div class="metric"><div class="label">Stale</div><div id="sStale" class="value">—</div></div></div><div id="semanticNote" class="muted small" style="margin-top:10px">Loading semantic coverage…</div></div></section>
<section class="panel flat" style="margin-top:18px"><div class="section-head"><div><h2>Production deployment control</h2><div class="muted small">OFF by default. Canary exposure is article-only, deterministically bucketed, approval-gated and protected by an automatic latency/error circuit breaker.</div></div><div class="toolbar"><button id="reloadDeployment" class="secondary" type="button">Reload</button><button id="rollbackDeployment" class="danger" type="button" {hidden}>Emergency pause</button><button id="configureDeployment" type="button" {hidden}>Configure rollout</button></div></div><div id="deploymentBox"><div class="skeleton" style="height:110px"></div></div><div id="deploymentHistory" class="stack" style="margin-top:10px"></div></section>
<section class="grid two" style="margin-top:18px"><div class="panel flat"><div class="section-head"><h2>Latest benchmark</h2></div><div id="runBox"><div class="empty">Load a benchmark set.</div></div><div id="runHistory" class="stack" style="margin-top:12px"></div><div id="compareBox" class="notice" style="margin-top:12px">Run both modes to compare ranking quality and latency.</div></div><div class="panel flat"><div class="section-head"><h2>Benchmark queries</h2><button id="newQueryBtn" class="secondary" type="button" {hidden}>Add query</button></div><div id="queryBox" class="stack"><div class="empty">No query set loaded.</div></div></div></section>
<section class="panel flat" style="margin-top:18px"><div class="section-head"><div><h2>Slow-query diagnostics</h2><div class="muted small">Privacy-preserving fingerprint groups; raw query strings are not stored.</div></div><button id="reloadSlow" class="secondary" type="button">Reload</button></div><div id="slowBox" class="stack"><div class="skeleton" style="height:90px"></div></div></section>
<dialog id="queryDialog"><form method="dialog" class="dialog-card"><div class="section-head"><h2>Add benchmark query</h2><button class="ghost" value="cancel">Close</button></div><label>Query<input id="bQuery" maxlength="500"/></label><label>Result type<select id="bType"><option value="all">All</option><option value="event">Event</option><option value="article">Article</option><option value="claim">Claim</option><option value="entity">Entity</option></select></label><label>Language<input id="bLanguage" maxlength="35" placeholder="en, hi…"/></label><label>Topic<input id="bTopic" maxlength="80"/></label><label>Notes<textarea id="bNotes" maxlength="2000"></textarea></label><button id="saveBenchmarkQuery" type="button">Add query</button></form></dialog>
<dialog id="importDialog"><form method="dialog" class="dialog-card"><div class="section-head"><h2>Import benchmark JSON</h2><button class="ghost" value="cancel">Close</button></div><div class="notice">Import merges queries by stable case key and upserts included relevance judgments into the benchmark set selected above.</div><label>Benchmark JSON file<input id="benchmarkFile" type="file" accept="application/json,.json"/></label><button id="confirmImport" type="button">Import benchmark</button></form></dialog>
<dialog id="judgmentDialog"><form method="dialog" class="dialog-card"><div class="section-head"><h2>Add relevance judgment</h2><button class="ghost" value="cancel">Close</button></div><input id="jQueryId" type="hidden"/><label>Result type<select id="jType"><option value="event">Event</option><option value="article">Article</option><option value="claim">Claim</option><option value="entity">Entity</option></select></label><label>Result UUID<input id="jResultId" placeholder="UUID"/></label><label>Relevance grade<select id="jGrade"><option value="3">3 · Highly relevant</option><option value="2">2 · Relevant</option><option value="1">1 · Marginal</option><option value="0">0 · Not relevant</option></select></label><label>Rationale<textarea id="jRationale" maxlength="2000"></textarea></label><button id="saveJudgment" type="button">Save judgment</button></form></dialog>
<dialog id="promotionDecisionDialog"><form method="dialog" class="dialog-card"><div class="section-head"><h2>Record release decision</h2><button class="ghost" value="cancel">Close</button></div><div class="notice">This records human governance only. It does not deploy or enable hybrid search.</div><input id="promotionEvaluationId" type="hidden"/><label>Decision<select id="promotionDecision"><option value="approve_candidate">Approve as release candidate</option><option value="hold">Hold</option><option value="reject">Reject</option></select></label><label>Rationale<textarea id="promotionDecisionRationale" maxlength="4000" placeholder="Why is this decision appropriate for the evidence and operational risk?"></textarea></label><button id="savePromotionDecision" type="button">Record decision</button></form></dialog>
<dialog id="promotionPolicyDialog"><form method="dialog" class="dialog-card"><div class="section-head"><h2>Search promotion policy</h2><button class="ghost" value="cancel">Close</button></div><div class="notice">These thresholds gate a recommendation only. Saving or passing this policy never changes production search mode.</div><label>Policy name<input id="pName" maxlength="160"/></label><div class="grid two"><label>Minimum queries<input id="pMinQueries" type="number" min="1" max="10000"/></label><label>Minimum judged coverage<input id="pJudgmentCoverage" type="number" min="0" max="1" step="0.01"/></label><label>Minimum relevant-query coverage<input id="pRelevantCoverage" type="number" min="0" max="1" step="0.01"/></label><label>Minimum NDCG@10 delta<input id="pNdcgDelta" type="number" min="-1" max="1" step="0.001"/></label><label>Minimum MRR delta<input id="pMrrDelta" type="number" min="-1" max="1" step="0.001"/></label><label>Minimum Recall@10 delta<input id="pRecallDelta" type="number" min="-1" max="1" step="0.001"/></label><label>Maximum hybrid p95 ms<input id="pMaxP95" type="number" min="1" max="120000" step="1"/></label><label>Maximum p95 regression ms<input id="pMaxP95Regression" type="number" min="0" max="120000" step="1"/></label><label>Minimum semantic coverage<input id="pSemanticCoverage" type="number" min="0" max="1" step="0.01"/></label><label>Minimum judged queries / slice<input id="pSliceQueries" type="number" min="1" max="10000"/></label><label>Maximum slice NDCG drop<input id="pSliceDrop" type="number" min="0" max="1" step="0.001"/></label></div><label>Required languages (comma separated)<input id="pLanguages" placeholder="en, hi"/></label><label>Required topics (comma separated)<input id="pTopics" placeholder="coal, finance"/></label><button id="savePromotionPolicy" type="button">Save policy</button></form></dialog>
<dialog id="rollbackDeploymentDialog"><form method="dialog" class="dialog-card"><div class="section-head"><h2>Emergency pause</h2><button class="ghost" value="cancel">Close</button></div><div class="error-box">Immediately sets rollout exposure to 0% and serves lexical search only. Existing benchmark/governance records are preserved.</div><label>Pause rationale<textarea id="rollbackRationale" maxlength="4000" placeholder="Why must the rollout be paused now?"></textarea></label><button id="confirmRollback" class="danger" type="button">Pause production reranking</button></form></dialog>
<dialog id="deploymentDialog"><form method="dialog" class="dialog-card"><div class="section-head"><h2>Production search rollout</h2><button class="ghost" value="cancel">Close</button></div><div class="notice">Production starts at OFF / 0%. SHADOW and CANARY require an active human approve-candidate decision. CANARY currently applies only to article-only searches. Circuit-breaker breaches auto-pause when enabled.</div><label>State<select id="dState"><option value="off">OFF · lexical only</option><option value="shadow">SHADOW · compute hybrid, serve lexical (adds semantic-path latency)</option><option value="canary">CANARY · serve hybrid to bucketed users</option><option value="paused">PAUSED · lexical only</option></select></label><label>Approved promotion decision<select id="dDecision"><option value="">None</option></select></label><div class="grid two"><label>Target exposure %<input id="dPercent" type="number" min="0" max="100" step="0.1" value="0"/></label><label>Circuit window minutes<input id="dWindow" type="number" min="1" max="1440" value="15"/></label><label>Max hybrid p95 ms<input id="dP95" type="number" min="1" max="120000" value="1500"/></label><label>Max hybrid error rate<input id="dError" type="number" min="0" max="1" step="0.001" value="0.05"/></label><label>Minimum hybrid samples<input id="dSamples" type="number" min="1" max="100000" value="30"/></label><label><input id="dAutoPause" type="checkbox" checked/> Auto-pause on circuit breach</label></div><label>Change rationale<textarea id="dRationale" maxlength="4000" placeholder="Why is this rollout change appropriate now?"></textarea></label><button id="saveDeployment" type="button">Apply rollout configuration</button></form></dialog>
<dialog id="reviewDialog"><div class="dialog-card review-dialog"><div class="section-head"><div><div class="eyebrow">Top ranked results</div><h2 id="reviewTitle">Review query</h2></div><button id="closeReview" class="ghost" type="button">Close</button></div><div class="notice">Grade 0 means not relevant; 1 marginal; 2 relevant; 3 highly relevant. Unjudged results are not positive evidence for search quality.</div><div id="reviewResults" class="stack"><div class="skeleton" style="height:100px"></div></div></div></dialog>
"""
    scripts = (
        f"<script>{COMMON_JS}\nconst canManage={'true' if can_manage else 'false'};let promotionDecisions=[];let deploymentStatus=null;let benchmarkQueries=[];\n"
        + r"""
async function loadExperimentStatus(){
  const box=document.getElementById('experimentStatus'),select=document.getElementById('evaluationMode');
  try{
    const d=await niApi('/api/v1/search-quality/experiment-status');
    const hybrid=select.querySelector('option[value="hybrid_article_rerank"]');
    hybrid.disabled=!d.semantic_experiment_available;
    box.innerHTML=d.semantic_experiment_available?`<b>Controlled semantic experiment available.</b> Model ${niEsc(d.embedding_model||'local')} · collection ${niEsc(d.qdrant_collection||'—')} · article-only · production remains ${niEsc(d.production_search_mode)}.`:`<b>Semantic experiment unavailable.</b> Production remains ${niEsc(d.production_search_mode)}. Enable local semantic indexing only if you intend to benchmark hybrid reranking.`;
  }catch(e){box.textContent='Could not load semantic experiment status.'}
}
async function loadTelemetry(){
  try{
    const d=await niApi('/api/v1/search-quality/telemetry?window_hours=24');
    document.getElementById('qObs').textContent=d.observation_count;
    document.getElementById('qP50').textContent=d.p50_ms==null?'—':`${Math.round(d.p50_ms)} ms`;
    document.getElementById('qP95').textContent=d.p95_ms==null?'—':`${Math.round(d.p95_ms)} ms`;
    document.getElementById('qSlow').textContent=d.slow_over_1500_ms;
  }catch(e){niToast(e.message,'bad')}
}
async function loadSlow(){
  try{const d=await niApi('/api/v1/search-quality/slow-diagnostics?window_hours=24&threshold_ms=750&limit=20');const box=document.getElementById('slowBox');box.innerHTML=d.groups.length?d.groups.map(g=>`<div class="evidence-item"><div class="pill-row">${niPill(niTitle(g.result_type),'neutral')}${niPill(`${g.observation_count} observations`,'warn')}</div><b>Fingerprint ${niEsc(g.query_fingerprint)}</b><div class="muted small">p50 ${Math.round(g.p50_ms)} ms · p95 ${Math.round(g.p95_ms)} ms · max ${Math.round(g.max_ms)} ms · cursor ${(g.cursor_page_ratio*100).toFixed(0)}%</div><div class="muted small">Filters: ${niEsc(JSON.stringify(g.filters||{}))}</div><ul class="compact">${(g.diagnosis||[]).map(x=>`<li>${niEsc(x)}</li>`).join('')}</ul></div>`).join(''):'<div class="empty">No search fingerprints crossed the 750 ms threshold in this window.</div>'}catch(e){document.getElementById('slowBox').innerHTML=`<div class="error-box">${niEsc(e.message)}</div>`}
}
function sliceSummary(slices){if(!slices||typeof slices!=='object')return '';return Object.entries(slices).map(([dimension,groups])=>`<div style="margin-top:12px"><b>${niEsc(niTitle(dimension))} slices</b><div class="stack" style="margin-top:6px">${Object.entries(groups||{}).map(([label,m])=>`<div class="muted small"><b>${niEsc(label)}</b> · ${m.query_count||0} queries · judged ${m.judged_query_count||0} · NDCG@10 ${typeof m['ndcg@10']==='number'?m['ndcg@10'].toFixed(3):'—'} · Recall@10 ${typeof m['recall@10']==='number'?m['recall@10'].toFixed(3):'—'}</div>`).join('')}</div></div>`).join('')}
function metricLine(k,v){
  return `<div class="dimension"><div>${niEsc(k)}</div><div class="bar"><span style="width:${Math.max(0,Math.min(100,Number(v||0)*100))}%"></span></div><b>${typeof v==='number'?v.toFixed(3):niEsc(v)}</b></div>`;
}
function searchHrefForQuery(q){
  const p=new URLSearchParams({q:q.query_text});
  const f=q.filters||{};
  const type=q.result_type||f.result_type||'all';
  if(type!=='all')p.set('type',type);
  for(const key of ['language','publisher','lifecycle_status','from_date','to_date']){
    if(f[key])p.set(key,String(f[key]).slice(0,key.includes('date')?10:500));
  }
  return `/search?${p.toString()}`;
}
function resultHref(item){
  if(item.result_type==='event')return `/events/${item.event_id||item.id}/intelligence`;
  if(item.result_type==='claim')return `/claims/${item.id}/investigation`;
  if(item.result_type==='entity')return `/entities/${item.id}/intelligence`;
  if(item.article_id)return `/articles/${item.article_id}/intelligence`;
  return '#';
}
async function saveQuickGrade(queryId,item,grade){
  await niApi(`/api/v1/search-quality/queries/${queryId}/judgments`,{
    method:'POST',
    body:JSON.stringify({result_type:item.result_type,result_id:item.id,relevance_grade:Number(grade),rationale:null})
  });
}
async function reviewQuery(queryId){
  const q=benchmarkQueries.find(x=>x.id===queryId);
  if(!q)return;
  document.getElementById('reviewTitle').textContent=q.query_text;
  const box=document.getElementById('reviewResults');
  box.innerHTML='<div class="skeleton" style="height:120px"></div>';
  document.getElementById('reviewDialog').showModal();
  try{
    const f=q.filters||{};
    const p=new URLSearchParams({q:q.query_text,limit:'20',result_type:q.result_type||f.result_type||'all'});
    for(const key of ['language','publisher','lifecycle_status'])if(f[key])p.set(key,String(f[key]));
    if(f.from_date)p.set('from_date',String(f.from_date).slice(0,10));
    if(f.to_date)p.set('to_date',String(f.to_date).slice(0,10));
    const [search,judgments]=await Promise.all([
      niApi(`/api/v1/search?${p.toString()}`),
      niApi(`/api/v1/search-quality/queries/${queryId}/judgments`)
    ]);
    const grades=new Map(judgments.map(j=>[`${j.result_type}:${j.result_id}`,j.relevance_grade]));
    box.innerHTML=search.results.length?search.results.map(item=>{
      const key=`${item.result_type}:${item.id}`;
      const g=grades.get(key);
      const gradeButtons=canManage?`<div class="grade-row">${[0,1,2,3].map(v=>`<button type="button" class="grade-btn ${g===v?'active':''}" data-query="${niEsc(queryId)}" data-type="${niEsc(item.result_type)}" data-result="${niEsc(item.id)}" data-grade="${v}" title="Set relevance grade ${v}">${v}</button>`).join('')}</div>`:'';
      return `<div class="review-result"><div><div class="pill-row">${niPill(niTitle(item.result_type),'neutral')}${g!==undefined?niPill(`Grade ${g}`,g>=2?'good':g===1?'warn':'bad'):niPill('Unjudged','neutral')}</div><b><a href="${resultHref(item)}">${niEsc(item.title)}</a></b>${item.snippet?`<div class="muted small review-snippet">${niEsc(item.snippet)}</div>`:''}</div>${gradeButtons}</div>`;
    }).join(''):'<div class="empty">No ranked results for this query.</div>';
    box.querySelectorAll('.grade-btn').forEach(btn=>btn.onclick=async()=>{
      try{
        const item=search.results.find(x=>String(x.id)===btn.dataset.result&&x.result_type===btn.dataset.type);
        if(!item)return;
        await saveQuickGrade(queryId,item,btn.dataset.grade);
        await reviewQuery(queryId);
        await loadBenchmark();
      }catch(e){niToast(e.message,'bad')}
    });
  }catch(e){box.innerHTML=`<div class="error-box">${niEsc(e.message)}</div>`}
}
function gateKind(state){return state==='pass'?'good':state==='warn'?'warn':'bad'}
async function loadSemanticCoverage(){
  try{
    const d=await niApi('/api/v1/search-quality/semantic-coverage');
    document.getElementById('sCurrent').textContent=d.current_article_versions;
    document.getElementById('sFresh').textContent=d.fresh_article_versions;
    document.getElementById('sMissing').textContent=d.missing_article_versions;
    document.getElementById('sStale').textContent=d.stale_article_versions;
    document.getElementById('semanticNote').textContent=`Fresh coverage ${d.fresh_coverage==null?'—':(d.fresh_coverage*100).toFixed(1)+'%'} · indexed ${d.indexed_coverage==null?'—':(d.indexed_coverage*100).toFixed(1)+'%'} · expected model ${d.expected_model||'not configured'}`;
  }catch(e){document.getElementById('semanticNote').textContent=e.message}
}
async function loadPromotion(){
  const set=document.getElementById('benchmarkSet').value.trim();if(!set)return;
  try{
    const [policy,history,decisions]=await Promise.all([
      niApi(`/api/v1/search-quality/${encodeURIComponent(set)}/promotion-policy`),
      niApi(`/api/v1/search-quality/${encodeURIComponent(set)}/promotion-gate/history?limit=6`),
      niApi(`/api/v1/search-quality/${encodeURIComponent(set)}/promotion-decisions?limit=6`)
    ]);
    window.currentPromotionPolicy=policy;
    promotionDecisions=decisions||[];
    const latest=history[0];
    window.latestPromotionEvaluation=latest||null;
    const box=document.getElementById('promotionBox');
    if(!latest){box.innerHTML=`<div class="empty">No gate evaluation yet. Policy ${niEsc(policy.persisted?'saved':'uses defaults until first evaluation')}.</div>`}
    else{
      const failed=(latest.failures||[]).map(x=>`<li>${niEsc(x)}</li>`).join('');
      const warnings=(latest.warnings||[]).map(x=>`<li>${niEsc(x)}</li>`).join('');
      box.innerHTML=`<div class="pill-row">${niPill(niTitle(latest.state),gateKind(latest.state))}${niPill(latest.methodology_version,'neutral')}</div><div style="margin-top:10px"><b>${latest.state==='pass'?'Thresholds met for human release review':'Promotion is not ready'}</b></div>${failed?`<div class="error-box" style="margin-top:8px"><ul class="compact">${failed}</ul></div>`:''}${warnings?`<div class="notice" style="margin-top:8px"><ul class="compact">${warnings}</ul></div>`:''}<div class="muted small" style="margin-top:8px">${niEsc(latest.interpretation||'')}</div>${canManage?`<div class="toolbar" style="margin-top:10px"><button id="recordPromotionDecision" class="secondary" type="button">Record human decision</button></div>`:''}`;
      const decisionButton=document.getElementById('recordPromotionDecision');if(decisionButton)decisionButton.onclick=()=>openPromotionDecision(latest);
    }
    const gateHistory=history.length?history.slice(0,5).map(x=>`<div class="muted small">${niPill(niTitle(x.state),gateKind(x.state))} ${niDate(x.created_at)} · ${(x.failures||[]).length} failures</div>`).join(''):'';
    const decisionHistory=decisions.length?`<div class="muted small" style="margin-top:8px"><b>Human decisions</b></div>${decisions.slice(0,5).map(x=>`<div class="muted small">${niPill(niTitle(x.decision.replaceAll('_',' ')),x.decision==='approve_candidate'?'good':x.decision==='reject'?'bad':'warn')} ${niDate(x.created_at)} · gate ${niEsc(x.gate_state)}</div>`).join('')}`:'';
    document.getElementById('promotionHistory').innerHTML=gateHistory+decisionHistory;
  }catch(e){document.getElementById('promotionBox').innerHTML=`<div class="error-box">${niEsc(e.message)}</div>`}
}
function openPromotionDecision(evaluation){
  document.getElementById('promotionEvaluationId').value=evaluation.id;
  const select=document.getElementById('promotionDecision');
  select.value=evaluation.state==='pass'?'approve_candidate':'hold';
  select.querySelector('option[value="approve_candidate"]').disabled=evaluation.state!=='pass';
  document.getElementById('promotionDecisionRationale').value='';
  document.getElementById('promotionDecisionDialog').showModal();
}
async function loadDeployment(){
  try{
    const d=await niApi('/api/v1/search/deployment');deploymentStatus=d;
    const c=d.config||{},t=d.telemetry||{};const state=(c.state||'off').toUpperCase();
    const kind=c.state==='canary'?'warn':c.state==='paused'?'bad':c.state==='shadow'?'neutral':'good';
    document.getElementById('deploymentBox').innerHTML=`<div class="pill-row">${niPill(state,kind)}${niPill(`${Number(c.target_percent||0).toFixed(1)}% target`,'neutral')}${niPill(d.circuit_breaker_state==='healthy'?'Circuit healthy':'Circuit tripped',d.circuit_breaker_state==='healthy'?'good':'bad')}</div><div class="grid four compact-grid" style="margin-top:10px"><div class="metric"><div class="label">Window samples</div><div class="value">${t.sample_count??0}</div></div><div class="metric"><div class="label">Hybrid served</div><div class="value">${t.hybrid_served_count??0}</div></div><div class="metric"><div class="label">Hybrid error rate</div><div class="value">${typeof t.hybrid_error_rate==='number'?(t.hybrid_error_rate*100).toFixed(1)+'%':'—'}</div></div><div class="metric"><div class="label">Hybrid p95</div><div class="value">${typeof t.hybrid_p95_ms==='number'?Math.round(t.hybrid_p95_ms)+' ms':'—'}</div></div></div><div class="muted small" style="margin-top:8px">Benchmark ${niEsc(c.benchmark_set||'—')} · Approval ${c.approval_active?'active':'inactive'} · Open-result outcomes ${t.open_outcome_count??0} · Shadow ${t.shadow_assigned_count??0} runs${typeof t.shadow_error_rate==='number'?` / ${(t.shadow_error_rate*100).toFixed(1)}% errors`:''}</div><div class="muted small" style="margin-top:4px">Open-result rate: lexical ${typeof t.lexical_open_rate==='number'?(t.lexical_open_rate*100).toFixed(1)+'%':'—'} · hybrid ${typeof t.hybrid_open_rate==='number'?(t.hybrid_open_rate*100).toFixed(1)+'%':'—'} · engagement proxy only, not relevance truth.</div><div class="muted small" style="margin-top:4px">${niEsc(d.interpretation||'')}</div>${(d.circuit_breaker_reasons||[]).length?`<div class="error-box" style="margin-top:8px">${(d.circuit_breaker_reasons||[]).map(niEsc).join('<br>')}</div>`:''}`;
    document.getElementById('deploymentHistory').innerHTML=(d.latest_actions||[]).length?`<div class="muted small"><b>Recent rollout actions</b></div>${d.latest_actions.map(a=>`<div class="muted small">${niEsc(a.action)} · ${niEsc(a.previous_state)} → ${niEsc(a.new_state)} · ${Number(a.target_percent||0).toFixed(1)}% · ${niEsc(a.rationale)} · ${niDate(a.created_at)}</div>`).join('')}`:'';
  }catch(e){document.getElementById('deploymentBox').innerHTML=`<div class="error-box">${niEsc(e.message)}</div>`}
}
function openDeploymentControl(){
  const c=deploymentStatus?.config||{};document.getElementById('dState').value=c.state||'off';document.getElementById('dPercent').value=c.target_percent??0;document.getElementById('dWindow').value=c.circuit_window_minutes??15;document.getElementById('dP95').value=c.max_hybrid_p95_ms??1500;document.getElementById('dError').value=c.max_hybrid_error_rate??0.05;document.getElementById('dSamples').value=c.min_hybrid_samples??30;document.getElementById('dAutoPause').checked=c.auto_pause!==false;document.getElementById('dRationale').value='';
  const select=document.getElementById('dDecision');const approved=(promotionDecisions||[]).filter(x=>x.decision==='approve_candidate'&&x.gate_state==='pass');select.innerHTML='<option value="">None</option>'+approved.map(x=>`<option value="${niEsc(x.id)}">${niEsc(x.benchmark_set)} · approved ${niDate(x.created_at)}</option>`).join('');if(c.promotion_decision_id)select.value=c.promotion_decision_id;document.getElementById('deploymentDialog').showModal();
}
function openPromotionPolicy(){
  const p=window.currentPromotionPolicy;if(!p)return;
  document.getElementById('pName').value=p.name||'';
  document.getElementById('pMinQueries').value=p.min_query_count;
  document.getElementById('pJudgmentCoverage').value=p.min_judgment_coverage;
  document.getElementById('pRelevantCoverage').value=p.min_relevant_query_coverage;
  document.getElementById('pNdcgDelta').value=p.min_ndcg_delta;
  document.getElementById('pMrrDelta').value=p.min_mrr_delta;
  document.getElementById('pRecallDelta').value=p.min_recall_delta;
  document.getElementById('pMaxP95').value=p.max_hybrid_p95_ms;
  document.getElementById('pMaxP95Regression').value=p.max_p95_regression_ms;
  document.getElementById('pSemanticCoverage').value=p.min_semantic_coverage;
  document.getElementById('pSliceQueries').value=p.min_slice_judged_queries;
  document.getElementById('pSliceDrop').value=p.max_slice_ndcg_drop;
  document.getElementById('pLanguages').value=(p.required_languages||[]).join(', ');
  document.getElementById('pTopics').value=(p.required_topics||[]).join(', ');
  document.getElementById('promotionPolicyDialog').showModal();
}
async function loadBenchmark(){
  const set=document.getElementById('benchmarkSet').value.trim();
  if(!set)return;
  try{
    const [queries,runs,comparison]=await Promise.all([
      niApi(`/api/v1/search-quality/${encodeURIComponent(set)}/queries`),
      niApi(`/api/v1/search-quality/${encodeURIComponent(set)}/runs?limit=10`),
      niApi(`/api/v1/search-quality/${encodeURIComponent(set)}/compare`)
    ]);
    benchmarkQueries=queries;
    document.getElementById('queryBox').innerHTML=queries.length?queries.map(q=>`<div class="evidence-item"><div class="pill-row">${niPill(niTitle(q.result_type),'neutral')}${niPill(`${q.relevant_judgment_count} relevant / ${q.judgment_count} judged`,q.judgment_count?'good':'warn')}</div><b>${niEsc(q.query_text)}</b>${q.topic_key?`<div class="muted small">Topic: ${niEsc(q.topic_key)}</div>`:''}<div class="toolbar" style="margin-top:8px"><a class="button ghost" href="${searchHrefForQuery(q)}">Open search</a>${canManage?`<button class="secondary review-query" data-id="${niEsc(q.id)}" type="button">Review ranked results</button><button class="ghost small-judgment" data-id="${niEsc(q.id)}" type="button">Manual judgment</button>`:''}</div></div>`).join(''):'<div class="empty">No benchmark queries in this set.</div>';
    document.querySelectorAll('.small-judgment').forEach(b=>b.onclick=()=>{
      document.getElementById('jQueryId').value=b.dataset.id;
      document.getElementById('judgmentDialog').showModal();
    });
    document.querySelectorAll('.review-query').forEach(b=>b.onclick=()=>reviewQuery(b.dataset.id));
    const r=runs[0];
    document.getElementById('runBox').innerHTML=r?`<div class="pill-row">${niPill(r.search_mode,'neutral')}${niPill(`${r.judged_query_count}/${r.query_count} judged`,r.judged_query_count===r.query_count?'good':'warn')}</div><div style="margin-top:10px">${Object.entries(r.metrics||{}).filter(([k,v])=>typeof v==='number').map(([k,v])=>metricLine(k,v)).join('')}${sliceSummary(r.metrics?.slices)}</div><div class="muted small" style="margin-top:10px">p50 ${r.latency?.p50_ms??'—'} ms · p95 ${r.latency?.p95_ms??'—'} ms · ${niDate(r.created_at)}</div>`:'<div class="empty">No benchmark run yet.</div>';
    document.getElementById('runHistory').innerHTML=runs.length>1?`<div class="muted small"><b>Recent runs</b></div>${runs.slice(0,6).map(x=>`<div class="muted small">${niEsc(x.search_mode)} · NDCG@10 ${typeof x.metrics?.['ndcg@10']==='number'?x.metrics['ndcg@10'].toFixed(3):'—'} · MRR ${typeof x.metrics?.mrr==='number'?x.metrics.mrr.toFixed(3):'—'} · p95 ${x.latency?.p95_ms??'—'} ms · ${niDate(x.created_at)}</div>`).join('')}`:'';
    const cbox=document.getElementById('compareBox');
    if(comparison.available){
      const d=comparison.metric_deltas||{},l=comparison.latency_deltas_ms||{};
      cbox.innerHTML=`<b>Hybrid vs lexical delta</b><div class="muted small" style="margin-top:5px">NDCG@10 ${typeof d['ndcg@10']==='number'?(d['ndcg@10']>=0?'+':'')+d['ndcg@10'].toFixed(3):'—'} · MRR ${typeof d.mrr==='number'?(d.mrr>=0?'+':'')+d.mrr.toFixed(3):'—'} · Recall@10 ${typeof d['recall@10']==='number'?(d['recall@10']>=0?'+':'')+d['recall@10'].toFixed(3):'—'} · p95 latency ${typeof l.p95_ms==='number'?(l.p95_ms>=0?'+':'')+Math.round(l.p95_ms)+' ms':'—'}</div><div class="muted small" style="margin-top:4px">${niEsc(comparison.note||'')}</div>`;
    }else cbox.textContent=comparison.note||'Run both modes to compare them.';
    await loadPromotion();
  }catch(e){niToast(e.message,'bad')}
}
if(canManage){
  document.getElementById('newQueryBtn').onclick=()=>document.getElementById('queryDialog').showModal();
  document.getElementById('saveBenchmarkQuery').onclick=async()=>{
    const set=document.getElementById('benchmarkSet').value.trim();
    const query=document.getElementById('bQuery').value.trim();
    try{
      await niApi('/api/v1/search-quality/queries',{
        method:'POST',
        body:JSON.stringify({benchmark_set:set,query_text:query,result_type:document.getElementById('bType').value,language:document.getElementById('bLanguage').value.trim()||null,topic_key:document.getElementById('bTopic').value.trim()||null,notes:document.getElementById('bNotes').value.trim()||null,filters:{}})
      });
      document.getElementById('queryDialog').close();
      await loadBenchmark();
    }catch(e){niToast(e.message,'bad')}
  };
  document.getElementById('saveJudgment').onclick=async()=>{
    try{
      await niApi(`/api/v1/search-quality/queries/${document.getElementById('jQueryId').value}/judgments`,{
        method:'POST',
        body:JSON.stringify({result_type:document.getElementById('jType').value,result_id:document.getElementById('jResultId').value.trim(),relevance_grade:Number(document.getElementById('jGrade').value),rationale:document.getElementById('jRationale').value.trim()||null})
      });
      document.getElementById('judgmentDialog').close();
      await loadBenchmark();
    }catch(e){niToast(e.message,'bad')}
  };
  document.getElementById('evaluateBenchmark').onclick=async()=>{
    const set=document.getElementById('benchmarkSet').value.trim();
    const b=document.getElementById('evaluateBenchmark');
    b.disabled=true;
    try{
      const mode=document.getElementById('evaluationMode').value;
      await niApi(`/api/v1/search-quality/${encodeURIComponent(set)}/evaluate`,{method:'POST',body:JSON.stringify({search_mode:mode,k_values:[1,3,5,10],max_results:20})});
      niToast(mode==='hybrid_article_rerank'?'Hybrid reranking experiment evaluated':'Lexical search benchmark evaluated','good');
      await loadBenchmark();
    }catch(e){niToast(e.message,'bad')}finally{b.disabled=false}
  };
  document.getElementById('editPromotionPolicy').onclick=openPromotionPolicy;
  document.getElementById('savePromotionPolicy').onclick=async()=>{
    const set=document.getElementById('benchmarkSet').value.trim();
    const split=id=>document.getElementById(id).value.split(',').map(x=>x.trim()).filter(Boolean);
    const payload={name:document.getElementById('pName').value.trim(),min_query_count:Number(document.getElementById('pMinQueries').value),min_judgment_coverage:Number(document.getElementById('pJudgmentCoverage').value),min_relevant_query_coverage:Number(document.getElementById('pRelevantCoverage').value),min_ndcg_delta:Number(document.getElementById('pNdcgDelta').value),min_mrr_delta:Number(document.getElementById('pMrrDelta').value),min_recall_delta:Number(document.getElementById('pRecallDelta').value),max_hybrid_p95_ms:Number(document.getElementById('pMaxP95').value),max_p95_regression_ms:Number(document.getElementById('pMaxP95Regression').value),min_semantic_coverage:Number(document.getElementById('pSemanticCoverage').value),min_slice_judged_queries:Number(document.getElementById('pSliceQueries').value),max_slice_ndcg_drop:Number(document.getElementById('pSliceDrop').value),required_languages:split('pLanguages'),required_topics:split('pTopics')};
    try{await niApi(`/api/v1/search-quality/${encodeURIComponent(set)}/promotion-policy`,{method:'PUT',body:JSON.stringify(payload)});document.getElementById('promotionPolicyDialog').close();niToast('Promotion policy saved','good');await loadPromotion()}catch(e){niToast(e.message,'bad')}
  };
  document.getElementById('evaluatePromotion').onclick=async()=>{const set=document.getElementById('benchmarkSet').value.trim();const b=document.getElementById('evaluatePromotion');b.disabled=true;try{const r=await niApi(`/api/v1/search-quality/${encodeURIComponent(set)}/promotion-gate/evaluate`,{method:'POST'});niToast(`Promotion gate: ${r.state}`,r.state==='pass'?'good':'warn');await Promise.all([loadPromotion(),loadSemanticCoverage()])}catch(e){niToast(e.message,'bad')}finally{b.disabled=false}};
  document.getElementById('savePromotionDecision').onclick=async()=>{const evaluationId=document.getElementById('promotionEvaluationId').value;const rationale=document.getElementById('promotionDecisionRationale').value.trim();if(rationale.length<5){niToast('Add a decision rationale','bad');return}try{await niApi(`/api/v1/search-quality/promotion-gate/${encodeURIComponent(evaluationId)}/decisions`,{method:'POST',body:JSON.stringify({decision:document.getElementById('promotionDecision').value,rationale})});document.getElementById('promotionDecisionDialog').close();niToast('Human release decision recorded','good');await Promise.all([loadPromotion(),loadDeployment()])}catch(e){niToast(e.message,'bad')}};
  document.getElementById('configureDeployment').onclick=openDeploymentControl;
  document.getElementById('rollbackDeployment').onclick=()=>{document.getElementById('rollbackRationale').value='';document.getElementById('rollbackDeploymentDialog').showModal()};
  document.getElementById('confirmRollback').onclick=async()=>{const rationale=document.getElementById('rollbackRationale').value.trim();if(rationale.length<5){niToast('Add a pause rationale','bad');return}try{await niApi('/api/v1/search/deployment/rollback',{method:'POST',body:JSON.stringify({rationale})});document.getElementById('rollbackDeploymentDialog').close();niToast('Production reranking paused; lexical search is serving','warn');await loadDeployment()}catch(e){niToast(e.message,'bad')}};
  document.getElementById('saveDeployment').onclick=async()=>{const rationale=document.getElementById('dRationale').value.trim();if(rationale.length<5){niToast('Add a rollout rationale','bad');return}const payload={state:document.getElementById('dState').value,target_percent:Number(document.getElementById('dPercent').value||0),promotion_decision_id:document.getElementById('dDecision').value||null,max_hybrid_p95_ms:Number(document.getElementById('dP95').value),max_hybrid_error_rate:Number(document.getElementById('dError').value),min_hybrid_samples:Number(document.getElementById('dSamples').value),circuit_window_minutes:Number(document.getElementById('dWindow').value),auto_pause:document.getElementById('dAutoPause').checked,rationale};try{await niApi('/api/v1/search/deployment',{method:'PUT',body:JSON.stringify(payload)});document.getElementById('deploymentDialog').close();niToast('Production rollout configuration updated','good');await loadDeployment()}catch(e){niToast(e.message,'bad')}};
}
document.getElementById('exportBenchmark').onclick=async()=>{const set=document.getElementById('benchmarkSet').value.trim();if(!set)return;try{const d=await niApi(`/api/v1/search-quality/${encodeURIComponent(set)}/export`);const blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`${set}.search-benchmark.json`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}catch(e){niToast(e.message,'bad')}};
if(canManage){document.getElementById('importBenchmark').onclick=()=>document.getElementById('importDialog').showModal();document.getElementById('confirmImport').onclick=async()=>{const file=document.getElementById('benchmarkFile').files?.[0];if(!file){niToast('Choose a JSON benchmark file','bad');return}try{const payload=JSON.parse(await file.text());const set=document.getElementById('benchmarkSet').value.trim()||payload.benchmark_set;const r=await niApi('/api/v1/search-quality/import',{method:'POST',body:JSON.stringify({benchmark_set:set,queries:payload.queries||[]})});document.getElementById('importDialog').close();niToast(`Imported ${r.query_count} queries and ${r.judgment_count} judgments`,'good');await loadBenchmark()}catch(e){niToast(e.message,'bad')}}}
document.getElementById('reloadSlow').onclick=loadSlow;
document.getElementById('reloadSemantic').onclick=loadSemanticCoverage;
document.getElementById('reloadDeployment').onclick=loadDeployment;
document.getElementById('closeReview').onclick=()=>document.getElementById('reviewDialog').close();
document.getElementById('loadBenchmark').onclick=loadBenchmark;
loadExperimentStatus();
loadTelemetry();
loadSlow();
loadSemanticCoverage();
loadDeployment();
loadBenchmark();
"""
        + "</script>"
    )
    extra_css = ".review-dialog{width:min(900px,calc(100vw - 36px));max-height:85vh;overflow:auto}.review-result{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;padding:13px;border:1px solid var(--line);border-radius:12px}.review-snippet{margin-top:6px}.grade-row{display:flex;gap:5px;align-items:center}.grade-btn{min-width:38px;padding:0 10px}.grade-btn.active{background:var(--good);box-shadow:0 0 0 3px var(--good-bg)}.compact-grid{gap:8px}.compact-grid .metric{padding:12px}@media(max-width:700px){.review-result{grid-template-columns:1fr}.compact-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}"
    return render_app_page(
        title="Search Quality",
        body=body,
        active="search-quality",
        role=role,
        scripts=scripts,
        extra_css=extra_css,
    )
