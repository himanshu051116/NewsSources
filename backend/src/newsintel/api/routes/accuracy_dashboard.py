# ruff: noqa: E501
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from newsintel.api.dependencies import AnalystAuth
from newsintel.api.ui import COMMON_JS, render_app_page

router = APIRouter(tags=["accuracy-dashboard"])


@router.get("/accuracy", response_class=HTMLResponse)
async def accuracy_dashboard(auth: AnalystAuth) -> str:
    role = getattr(getattr(auth, "role", None), "value", "analyst")
    body = r"""
<section class="page-head"><div><div class="eyebrow">Held-out validation</div><h1>Verification quality</h1><p class="lead">See how well claim assessments agree with reviewed benchmark cases, including cases where the system made no decision.</p></div></section>
<section class="panel stack">
  <div class="toolbar grow"><label>Benchmark set<input id="benchmarkSet" value="local-held-out-v2" maxlength="120" /></label><button id="loadButton" type="button">Load report</button></div>
  <div class="notice">These numbers apply only to the selected adjudicated benchmark. They are not a universal “news accuracy percentage”. New benchmarks should use blind double-review plus separate adjudication for disagreements.</div>
  <div id="message" class="muted small" aria-live="polite"></div>
</section>
<section class="grid four" style="margin-top:16px" id="metrics">
  <div class="metric"><div class="label">Decided-case accuracy</div><div class="value">—</div><div class="hint">Accuracy when a substantive verdict was rendered</div></div>
  <div class="metric"><div class="label">Decision coverage</div><div class="value">—</div><div class="hint">Share of adjudicated cases receiving a substantive verdict</div></div>
  <div class="metric"><div class="label">Macro F1</div><div class="value">—</div><div class="hint">Balanced across benchmark labels</div></div>
  <div class="metric"><div class="label">Unsafe high-confidence errors</div><div class="value">—</div><div class="hint">Wrong substantive verdicts at confidence ≥ 0.80</div></div>
</section>
<section class="grid two" style="margin-top:16px">
  <div class="panel"><div class="section-head"><h2>Benchmark corpus</h2><span id="readiness"></span></div><div id="audit"><div class="skeleton" style="height:100px"></div></div></div>
  <div class="panel"><div class="section-head"><h2>Release quality gate</h2><span id="gateState"></span></div><div id="gate"><div class="skeleton" style="height:100px"></div></div></div>
</section>
<section class="panel" style="margin-top:16px"><div class="section-head"><div><h2>Golden-corpus validation</h2><div class="muted small">Confidence intervals, slice gates and active-sampling targets for the held-out test split.</div></div><span id="validationState"></span></div><div id="validation"><div class="skeleton" style="height:120px"></div></div></section>
<section class="grid two" style="margin-top:16px">
  <div class="panel"><div class="section-head"><div><h2>Human adjudication agreement</h2><div class="muted small">Independent reviewer consistency before consensus finalization.</div></div></div><div id="agreement"><div class="skeleton" style="height:100px"></div></div></div>
  <div class="panel"><div class="section-head"><div><h2>Error attribution</h2><div class="muted small">Likely upstream weakness categories for wrong held-out verdicts.</div></div><button id="diagnosticsButton" class="secondary" type="button">Run diagnostics</button></div><div id="diagnostics"><div class="empty">Run diagnostics after finalized benchmark cases exist.</div></div></div>
</section>
<section class="panel" style="margin-top:16px"><div class="section-head"><div><h2>Evaluation history</h2><div class="muted small">Newest benchmark assessment first.</div></div></div><div id="history" class="table-wrap"><div class="empty">Load a benchmark set.</div></div></section>
"""
    scripts = "<script>" + COMMON_JS + r"""
function pct(v){return typeof v==='number'?`${(v*100).toFixed(1)}%`:'—'}
function metric(label,value,hint){return `<div class="metric"><div class="label">${niEsc(label)}</div><div class="value">${niEsc(value)}</div><div class="hint">${niEsc(hint)}</div></div>`}
function list(items){return items?.length?`<ul>${items.map(x=>`<li>${niEsc(x)}</li>`).join('')}</ul>`:'<div class="muted small">None</div>'}
function agreementHtml(a){if(!a||!a.review_count)return '<div class="empty">No blind-review agreement data exists yet.</div>';return `<div class="grid two"><div><b>${a.multi_review_case_count}</b><div class="muted small">multi-review cases</div></div><div><b>${a.disagreement_case_count}</b><div class="muted small">reviewer disagreements</div></div></div><div style="margin-top:12px"><b>Pairwise agreement</b><div>${pct(a.pairwise_agreement)}</div></div><div style="margin-top:8px"><b>Krippendorff alpha</b><div>${typeof a.krippendorff_alpha_nominal==='number'?a.krippendorff_alpha_nominal.toFixed(3):'—'}</div></div><div class="muted small" style="margin-top:10px">Agreement measures reviewer consistency, not model accuracy.</div>`}
async function loadAccuracy(){
  const set=document.getElementById('benchmarkSet').value.trim();
  if(set.length<2){document.getElementById('message').textContent='Enter a benchmark set name.';return}
  const btn=document.getElementById('loadButton');btn.disabled=true;document.getElementById('message').textContent='Loading adjudicated benchmark history…';
  try{
    const [evals,audit,gates,agreement,validation]=await Promise.all([
      niApi(`/api/v1/verification-benchmark/${encodeURIComponent(set)}`),
      niApi(`/api/v1/verification-benchmark/${encodeURIComponent(set)}/audit`),
      niApi(`/api/v1/verification-benchmark/${encodeURIComponent(set)}/quality-gate`),
      niOptional(`/api/v1/verification-benchmark/${encodeURIComponent(set)}/agreement`),
      niOptional(`/api/v1/verification-benchmark/${encodeURIComponent(set)}/validation-report`)
    ]);
    const latest=evals?.[0]||null;
    document.getElementById('metrics').innerHTML=latest?[
      metric('Decided-case accuracy',pct(latest.decided_accuracy),'Accuracy only where a substantive verdict was rendered'),
      metric('Decision coverage',pct(latest.decision_coverage),`Abstention: ${pct(latest.abstention_rate)}`),
      metric('Macro F1',pct(latest.macro_f1),'All benchmark labels'),
      metric('Unsafe high-confidence errors',pct(latest.unsafe_high_confidence_error_rate),'Wrong decided verdicts at confidence ≥ 0.80')
    ].join(''):[metric('Decided-case accuracy','—','No evaluation run exists yet'),metric('Decision coverage','—','No evaluation run exists yet'),metric('Macro F1','—','No evaluation run exists yet'),metric('Unsafe high-confidence errors','—','No evaluation run exists yet')];
    const r=audit.readiness||'unknown';document.getElementById('readiness').innerHTML=niPill(niTitle(r),r==='ready'?'good':'warn');
    document.getElementById('audit').innerHTML=`<div class="grid two"><div><b>${audit.case_count}</b><div class="muted small">adjudicated cases</div></div><div><b>${audit.split_counts?.test||0}</b><div class="muted small">held-out test cases</div></div></div><div style="margin-top:12px"><b>Leakage</b><div class="muted small">Identity: ${audit.leakage_case_count||0} · Group/event: ${audit.group_leakage_keys?.length||0} · Source-document: ${audit.source_document_leakage_keys?.length||0}</div></div><div style="margin-top:12px"><b>Audit warnings</b>${list(audit.warnings)}</div>`;
    const gate=gates?.[0]||null;document.getElementById('gateState').innerHTML=gate?niPill(niTitle(gate.state),gate.state==='pass'?'good':gate.state==='fail'?'bad':'warn'):niPill('Not run','neutral');
    document.getElementById('gate').innerHTML=gate?`<div><b>Failures</b>${list(gate.failures)}</div><div style="margin-top:12px"><b>Warnings</b>${list(gate.warnings)}</div>`:'<div class="empty">No quality-gate run exists for this benchmark set.</div>';

    if(validation){
      document.getElementById('validationState').innerHTML=niPill(niTitle(validation.overall_gate_state),validation.overall_gate_state==='pass'?'good':'bad');
      const ci=validation.decided_accuracy_interval||{};const targets=(validation.active_sampling_targets||[]).slice(0,6);
      document.getElementById('validation').innerHTML=`<div class="grid four"><div><b>${validation.corpus_case_count}</b><div class="muted small">test cases</div></div><div><b>${pct(validation.decided_accuracy)}</b><div class="muted small">decided accuracy</div></div><div><b>${typeof ci.lower==='number'?pct(ci.lower):'—'} – ${typeof ci.upper==='number'?pct(ci.upper):'—'}</b><div class="muted small">95% Wilson interval</div></div><div><b>${pct(validation.decision_coverage)}</b><div class="muted small">decision coverage</div></div></div><div style="margin-top:14px"><b>Corpus version</b><div class="muted small" style="word-break:break-all">${niEsc(validation.corpus_fingerprint)}</div></div><div style="margin-top:14px"><b>Next sampling priorities</b>${targets.length?`<div class="table-wrap"><table><thead><tr><th>Slice</th><th>Cases</th><th>Priority</th><th>Reason</th></tr></thead><tbody>${targets.map(x=>`<tr><td>${niEsc(niTitle(x.dimension))}: ${niEsc(x.value)}</td><td>${x.case_count}</td><td>${Math.round(x.priority*100)}</td><td>${niEsc(x.reason.replaceAll('_',' '))}</td></tr>`).join('')}</tbody></table></div>`:'<div class="muted small">No immediate slice-sampling priorities.</div>'}</div>`;
    }else{document.getElementById('validationState').innerHTML=niPill('Not measured','neutral');document.getElementById('validation').innerHTML='<div class="empty">No validation report available.</div>';}
    document.getElementById('agreement').innerHTML=agreementHtml(agreement);
    document.getElementById('history').innerHTML=evals?.length?`<table><thead><tr><th>Created</th><th>Cases</th><th>All-case accuracy</th><th>Decided accuracy</th><th>Coverage</th><th>Macro F1</th><th>High-conf error</th></tr></thead><tbody>${evals.map(x=>`<tr><td>${niDate(x.created_at)}</td><td>${x.observation_count}</td><td>${pct(x.accuracy)}</td><td>${pct(x.decided_accuracy)}</td><td>${pct(x.decision_coverage)}</td><td>${pct(x.macro_f1)}</td><td>${pct(x.unsafe_high_confidence_error_rate)}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">No benchmark evaluation exists yet. Finalize blind adjudications, then run the benchmark assessment.</div>';
    document.getElementById('message').textContent=latest?`Loaded ${latest.observation_count} evaluated cases for ${set}.`:'Benchmark corpus exists, but no evaluation run has been stored yet.';
  }catch(e){document.getElementById('message').innerHTML=`<span class="error-box">${niEsc(e.message)}</span>`}finally{btn.disabled=false}
}
async function runDiagnostics(){
  const set=document.getElementById('benchmarkSet').value.trim();const b=document.getElementById('diagnosticsButton');b.disabled=true;document.getElementById('diagnostics').innerHTML='<div class="skeleton" style="height:90px"></div>';
  try{const d=await niApi(`/api/v1/verification-benchmark/${encodeURIComponent(set)}/diagnostics`,{method:'POST'});const items=Object.entries(d.taxonomy_counts||{}).sort((a,b)=>b[1]-a[1]);document.getElementById('diagnostics').innerHTML=`<div><b>${d.error_count}</b> errors across ${d.case_count} finalized cases · ${pct(d.error_rate)}</div><div style="margin-top:12px">${items.length?items.map(([k,v])=>`<div class="toolbar between"><span>${niEsc(niTitle(k))}</span><b>${v}</b></div>`).join(''):'<div class="muted small">No wrong benchmark verdicts to attribute.</div>'}</div><div class="muted small" style="margin-top:12px">Diagnostic attribution prioritizes engineering investigation; it is not causal proof.</div>`}catch(e){document.getElementById('diagnostics').innerHTML=`<div class="error-box">${niEsc(e.status===403?'Claim-verifier access is required to run diagnostics.':e.message)}</div>`}finally{b.disabled=false}
}
document.getElementById('diagnosticsButton').addEventListener('click',runDiagnostics);document.getElementById('loadButton').addEventListener('click',loadAccuracy);document.getElementById('benchmarkSet').addEventListener('keydown',e=>{if(e.key==='Enter')loadAccuracy()});loadAccuracy();
</script>"""
    return render_app_page(title="Accuracy", body=body, active="accuracy", role=role, scripts=scripts)
