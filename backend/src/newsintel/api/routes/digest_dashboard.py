# ruff: noqa: E501
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from newsintel.api.dependencies import ViewerAuth
from newsintel.api.ui import COMMON_JS, render_app_page

router = APIRouter(tags=["news-digests"])

BODY = r"""
<style>
.brief-page{max-width:864px;margin:0 auto}.brief-head{align-items:center;margin-bottom:25px}.brief-head h1{font-size:clamp(28px,4vw,40px);margin:0;line-height:1.2}.brief-head .lead{font-size:15px;margin:10px 0 0;max-width:560px}.brief-head button{flex-shrink:0}
.brief-controls{margin-bottom:18px}.brief-controls .toolbar{justify-content:space-between}.brief-period{display:flex;gap:3px;padding:4px;border:1px solid var(--line);background:var(--surface-2);border-radius:12px}.brief-period button{background:transparent;color:var(--muted);min-width:83px;min-height:38px;border-radius:8px}.brief-period button.active{background:var(--surface);color:var(--brand);box-shadow:0 2px 6px rgba(0,0,0,.08)}
.brief-status-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:12px}.brief-status-row button{min-height:28px;padding:0 7px;font-weight:600}.brief-picker{display:flex;gap:12px;align-items:center;margin-top:13px;padding-top:13px;border-top:1px solid var(--line)}.brief-picker label{white-space:nowrap;font-size:13px}.brief-picker select{max-width:320px}
.brief-paper{padding:0 25px;background:var(--surface);border:1px solid var(--line);border-radius:16px;counter-reset:brief-story var(--start,0)}.brief-story{position:relative;padding:23px 0 23px 38px;border-bottom:1px solid var(--line);counter-increment:brief-story}.brief-story:last-child{border-bottom:0}.brief-story::before{content:counter(brief-story,decimal-leading-zero);position:absolute;left:0;top:27px;color:var(--muted);font-size:12px;font-weight:700}.brief-story h2,.brief-story h3{font-size:19px;line-height:1.4;margin:0 0 8px;letter-spacing:-.02em}.brief-story h2 a,.brief-story h3 a{color:var(--text)}.brief-story p{margin:0 0 11px;line-height:1.65;font-size:15px;color:var(--muted)}
.brief-byline{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;font-size:12px;color:var(--muted)}.brief-byline>span{font-weight:650}.brief-byline details{flex:1;min-width:120px}.brief-byline summary{cursor:pointer;width:fit-content;color:var(--brand)}.brief-source-info{padding-top:10px;line-height:1.7}.brief-source-info ul{padding-left:18px;margin:7px 0}.brief-source-info li{margin:7px 0}.brief-source-info .muted{font-size:12px}.brief-more{text-align:center;margin:20px 0}.brief-more button{min-width:200px}
.brief-about{margin-top:24px;padding:15px 0;border-top:1px solid var(--line);font-size:12px;color:var(--muted);line-height:1.7}.brief-about summary{cursor:pointer;width:fit-content}.brief-about p{margin:9px 0}.brief-about .notice{margin-top:12px}
.brief-refresh{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px}.brief-refresh button{flex-shrink:0}.brief-story a{overflow-wrap:anywhere}.brief-story .freshness-label{color:var(--warn);background:var(--warn-bg);padding:3px 7px;border-radius:5px}.brief-story .freshness-reason{color:var(--warn);font-size:13px}.brief-controls{background:var(--surface);border-radius:14px}.brief-paper{box-shadow:0 3px 18px rgba(22,37,64,.025)}.brief-byline summary{min-height:32px;display:flex;align-items:center}.brief-byline details{flex:0 1 auto;margin-left:auto}.brief-source-info{min-width:220px}.brief-scope{font-size:12px;color:var(--muted);margin:12px 0 0}
.brief-form{margin-bottom:20px}.brief-form fieldset{border:0;padding:0;margin:0}.brief-form legend{font-size:14px;font-weight:750;margin-bottom:9px}.brief-form .hint{font-size:12px;color:var(--muted);margin:0 0 12px}.brief-topics{display:flex;flex-wrap:wrap;gap:8px}.brief-topics label{display:flex;gap:7px;align-items:center;padding:9px 11px;background:var(--surface);border:1px solid var(--line);border-radius:10px;font-size:13px;cursor:pointer}.brief-topics label:has(input:checked){background:var(--brand-soft);border-color:var(--brand);color:var(--brand)}.brief-topics input,.brief-choice input{width:16px;height:16px;margin:0;flex-shrink:0;accent-color:var(--brand)}
.brief-form details{border-top:1px solid var(--line);padding-top:14px}.brief-form details>summary{cursor:pointer;font-size:13px;font-weight:700}.brief-options{padding-top:16px}.brief-choice-list{max-height:180px;overflow-y:auto;border:1px solid var(--line);border-radius:10px;padding:5px;margin-top:8px}.brief-choice{display:flex;gap:9px;align-items:center;padding:8px;font-size:13px;cursor:pointer}.brief-choice:has(input:checked){background:var(--brand-soft);border-radius:7px}.brief-choice-search{font-size:13px}.brief-field{display:grid;gap:6px;font-size:13px;font-weight:650}.brief-save{display:grid;gap:12px;padding-top:14px}.brief-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.brief-actions #applyBrief{min-width:150px}.brief-form #streamMessage:empty{display:none}.brief-form .section-head{margin-bottom:0}
@media(max-width:520px){.brief-head{flex-direction:row;align-items:flex-start;gap:10px}.brief-head h1{font-size:27px}.brief-head .lead{font-size:14px}.brief-head button{min-height:34px;padding:0 10px}.brief-controls{padding:14px!important}.brief-period button{min-width:70px;min-height:36px}.brief-paper{padding:0 16px}.brief-story{padding:20px 0 20px 28px}.brief-story::before{top:24px;font-size:11px}.brief-story h2,.brief-story h3{font-size:18px}.brief-picker{align-items:flex-start;flex-direction:column;gap:7px}.brief-picker select{max-width:none}.brief-topics label{padding:8px 9px;font-size:12px}.brief-byline{gap:8px}.brief-actions #applyBrief{flex:1}}
</style>
<div class="brief-page">
 <header class="page-head brief-head">
  <div><h1>Catch up in two minutes.</h1><p class="lead">The key headlines, with one useful line of context.<br>A quick daily read or a look back at the week.</p></div>
  <button id="refreshBrief" class="secondary" type="button" aria-label="Refresh news brief">Update</button>
 </header>
 <section class="panel brief-controls" aria-label="Choose your brief">
  <div class="toolbar">
   <div class="brief-period" role="group" aria-label="Reading period"><button class="active" id="dailyBrief" aria-pressed="true" type="button">Daily</button><button id="weeklyBrief" aria-pressed="false" type="button">Weekly</button></div>
   <button id="customizeBrief" class="secondary" aria-expanded="false" aria-controls="briefCustomize" type="button" disabled>Personalize</button>
  </div>
  <div class="brief-status-row"><span id="briefStatus" class="muted small" role="status" aria-live="polite">Getting your news…</span><button id="clearBrief" class="ghost" type="button" hidden>Clear filters</button></div>
  <p id="captureStatus" class="muted small" hidden></p>
  <div id="streamPicker" class="brief-picker" hidden><label for="streamSelect">My feeds</label><select id="streamSelect"><option value="">All news</option></select></div>
 </section>
 <div id="briefRefreshNotice" class="notice brief-refresh" hidden role="status"><span id="briefRefreshMessage"></span><button id="refreshStaleBrief" class="secondary" type="button">Update brief</button></div>
 <section id="briefCustomize" class="panel brief-form stack" hidden aria-label="Personalize your news">
  <div class="section-head"><h2>What interests you?</h2><button id="closeCustomize" class="ghost" type="button" aria-label="Close personalization">Close</button></div>
  <p class="hint">Your reading period and choices are remembered for your next visit.</p>
  <fieldset><legend class="sr-only">Topics</legend><p class="hint">Choose a few topics, or keep all news.</p><div class="brief-topics"><button id="allTopics" class="filter-chip active" aria-pressed="true" type="button">All topics</button><div id="briefTopics" class="brief-topics"></div></div></fieldset>
  <details id="moreOptions"><summary>More options</summary>
   <div class="brief-options stack">
    <div class="grid two">
     <fieldset><legend>Publishers</legend><p class="hint">All publishers unless you choose some.</p><input id="publisherSearch" type="search" class="brief-choice-search" placeholder="Find a publisher" aria-label="Find a publisher"><div id="briefPublishers" class="brief-choice-list"></div></fieldset>
     <fieldset><legend>Languages</legend><p class="hint">All languages unless you choose some.</p><input id="languageSearch" type="search" class="brief-choice-search" placeholder="Find a language" aria-label="Find a language"><div id="briefLanguages" class="brief-choice-list"></div></fieldset>
    </div>
    <div class="grid two">
     <label class="brief-field" for="briefKeywords">Include words or places<input id="briefKeywords" maxlength="1800" placeholder="e.g. Bengaluru, cricket"><span class="hint">Separate choices with commas. Any match is included.</span></label>
     <label class="brief-field" for="briefExclude">Hide stories mentioning<input id="briefExclude" maxlength="1800" placeholder="e.g. spoilers, celebrity"><span class="hint">Separate words or phrases with commas.</span></label>
    </div>
   </div>
  </details>
  <div class="brief-actions"><button id="applyBrief" type="button">Show my brief</button><button id="resetBrief" class="ghost" type="button">Reset</button></div>
  <details id="saveOptions"><summary>Save these choices</summary><div class="brief-save">
   <label for="streamName" class="brief-field">Feed name<input id="streamName" maxlength="80" placeholder="e.g. My morning news"></label>
   <div class="brief-actions"><button id="saveBrief" class="secondary" type="button">Save feed</button><button id="updateBrief" type="button" hidden>Save changes</button><button id="deleteBrief" class="ghost" type="button" hidden>Delete feed</button></div>
  </div></details>
  <div id="streamMessage" class="small" role="status" aria-live="polite"></div>
 </section>
 <div class="section-head"><h2 id="editionTitle" tabindex="-1">Your daily brief</h2><span class="pill neutral" id="readTime">About 2 min</span></div>
 <p id="editionFocus" class="muted small">Important developments from the last 24 hours.</p>
 <p class="brief-scope">A selection from connected publishers. Tap a headline to read the full story.</p>
 <div id="briefNotice" class="notice warn" hidden style="margin-bottom:14px"></div>
 <div id="captureWarning" class="notice warn" hidden style="margin-bottom:14px"></div>
 <div id="briefItems" class="brief-paper" aria-live="polite"><div class="empty">Getting your news…</div></div>
 <section id="keepReading" hidden>
  <div class="brief-more"><button id="showFullBrief" class="secondary" type="button" disabled>More headlines</button></div>
  <div id="fullBriefItems" class="brief-paper" hidden></div>
  <div class="brief-more"><button id="moreBrief" class="secondary" type="button" hidden>More headlines</button></div>
 </section>
 <details class="brief-about"><summary>About this brief</summary>
  <div id="briefCoverage">Checking coverage…</div>
  <p>This is a quick selection from the publishers captured by this platform. It does not include every headline. Use More headlines to keep reading.</p>
  <p>Each sentence is an excerpt from the named publisher, chosen to add detail to the headline. Open the story for context. Closely matching coverage is grouped, with all its sources available. Opinion and analysis are labelled; multiple sources do not by themselves verify a claim. Original reporting languages are preserved.</p>
  <p>The short brief prioritizes useful reporting, source variety and public-interest developments. Weekly also balances reporting across the week. Opinion, horoscope and shopping items stay in More headlines unless your selected topics or words include them. Archive reprints and captures without enough readable text stay out of the short brief.</p>
  <p>The short brief requires a publisher publication date within the last 24 hours or seven days. Capture and modification dates do not establish publication time. Undated reports, archive reprints and clearly expired live sessions stay in More headlines with a label. Common non-news pages are excluded.</p>
 </details>
</div>
"""

SCRIPT = r"""
const el=id=>document.getElementById(id);
let period='daily',streams=[],options={topics:[],publishers:[],languages:[]},applied={},edition=null,sequence=0,controller=null,nextOffset=null,fullBusy=false,fullShown=new Set(),previewLabel='',streamBusy=false,setupFailed=false;
let preferencesRestored=false,preferenceWrites=Promise.resolve();
const BRIEF_STALE_AFTER_MS=5*60*1000;
function snapshotIsStale(){return edition&&Date.now()-new Date(edition.window_end).getTime()>=BRIEF_STALE_AFTER_MS;}
function updateSnapshotNotice(){
 const stale=Boolean(snapshotIsStale());el('briefRefreshNotice').hidden=!stale;
 if(stale)el('briefRefreshMessage').textContent=`You are reading the brief as of ${new Date(edition.window_end).toLocaleString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}. Update it to check the latest captured reporting.`;
 return stale;
}
function checkSnapshotOnReturn(){
 if(document.visibilityState!=='visible'||!updateSnapshotNotice())return;
 const readingMore=!el('fullBriefItems').hidden||fullBusy;
 if(!streamBusy&&el('briefCustomize').hidden&&!readingMore)loadEdition();
}
function rememberChoices(){
 preferencesRestored=true;
 const selected=streams.find(s=>s.id===el('streamSelect').value);
 const filters=JSON.parse(JSON.stringify(applied));
 const streamId=selected&&JSON.stringify(selected.filters)===JSON.stringify(filters)?selected.id:null;
 const body=JSON.stringify({period,filters,stream_id:streamId});
 preferenceWrites=preferenceWrites.catch(()=>{}).then(()=>niApi('/api/v1/digests/preferences',{method:'PUT',body})).catch(()=>niToast('Your choices apply now, but could not be remembered for your next visit.','bad'));
}
const checked=id=>Array.from(el(id).querySelectorAll('input:checked')).map(input=>input.value);
function filtersFromForm(){return {topics:checked('briefTopics'),publisher_ids:checked('briefPublishers'),languages:checked('briefLanguages'),keywords:el('briefKeywords').value.split(',').map(s=>s.trim()).filter(Boolean),exclude_keywords:el('briefExclude').value.split(',').map(s=>s.trim()).filter(Boolean)};}
function syncTopics(){const all=!checked('briefTopics').length;el('allTopics').classList.toggle('active',all);el('allTopics').setAttribute('aria-pressed',String(all));}
function setForm(filters={}){
 for(const [id,key] of [['briefTopics','topics'],['briefPublishers','publisher_ids'],['briefLanguages','languages']])el(id).querySelectorAll('input').forEach(input=>input.checked=(filters[key]||[]).includes(input.value));
 el('briefKeywords').value=(filters.keywords||[]).join(', ');el('briefExclude').value=(filters.exclude_keywords||[]).join(', ');syncTopics();
}
function setPeriod(value){period=value;for(const p of ['daily','weekly']){el(p+'Brief').classList.toggle('active',value===p);el(p+'Brief').setAttribute('aria-pressed',String(value===p));}el('editionTitle').textContent=value==='daily'?'Your daily brief':'Your weekly brief';el('editionFocus').textContent=value==='daily'?'Important developments from the last 24 hours.':'Key developments across the last seven days.';}
function populateStreams(id=''){
 const selected=streams.find(stream=>stream.id===id),selectedId=selected?selected.id:'';
 el('streamSelect').replaceChildren(new Option('All news',''));for(const s of streams)el('streamSelect').add(new Option(s.name,s.id));el('streamSelect').value=selectedId;
 el('streamName').value=selected?selected.name:'';
 el('streamPicker').hidden=!streams.length;el('updateBrief').hidden=!selectedId;el('deleteBrief').hidden=!selectedId;el('saveBrief').textContent=selectedId?'Save as new feed':'Save feed';
}
function lockStreams(busy){streamBusy=busy;for(const id of ['streamSelect','dailyBrief','weeklyBrief','saveBrief','updateBrief','deleteBrief','applyBrief','resetBrief','clearBrief','allTopics'])el(id).disabled=busy;el('briefCustomize').querySelectorAll('input').forEach(input=>input.disabled=busy);}
function closeCustomize(){el('briefCustomize').hidden=true;el('customizeBrief').setAttribute('aria-expanded','false');el('customizeBrief').focus();}
function languageName(code){try{return new Intl.DisplayNames([navigator.language||'en'],{type:'language'}).of(code)||code;}catch{return code==='unknown'?'Unknown language':code;}}
function choice(value,label){return `<label class="brief-choice"><input type="checkbox" value="${niEsc(value)}"><span>${niEsc(label)}</span></label>`;}
function searchChoices(id,query){const term=query.trim().toLocaleLowerCase();el(id).querySelectorAll('label').forEach(label=>label.hidden=!label.textContent.toLocaleLowerCase().includes(term));}
function card(item,level='h2'){
 const primary=item.sources[0],url=primary.url?niSafeUrl(primary.url):`/articles/${niEsc(item.article_id)}/intelligence`;
 const attributes=primary.url?' target="_blank" rel="noopener noreferrer"':'';
 const topic=(options.topics.find(t=>t.key===item.topic)||{}).label||'';
 const kind={analysis:'Analysis',opinion:'Opinion',service:'Lifestyle & service',archive:'From the archives'}[item.report_type]||'';
 const date=new Date(item.published_at).toLocaleString([],{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});
 const freshness=item.freshness_status||(item.date_basis==='first_captured'?'date_unconfirmed':'current');
 const freshnessLabel={date_unconfirmed:'Publication date unconfirmed',expired:'Time-sensitive reporting has expired',historical:'Historical reporting'}[freshness]||'';
 const freshnessReason=freshnessLabel&&item.freshness_reason?`<p class="freshness-reason">${niEsc(item.freshness_reason)}</p>`:'';
 const links=item.sources.map(s=>`<li>${s.url?`<a href="${niEsc(niSafeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${niEsc(s.publisher_name)} ↗</a>`:niEsc(s.publisher_name)} · <a href="/articles/${niEsc(s.article_id)}/intelligence">Saved article</a></li>`).join('');
 return `<article class="brief-story"><${level}><a href="${niEsc(url)}"${attributes}>${niEsc(item.title)}</a></${level}><p>${niEsc(item.explanation)}</p>${freshnessReason}<div class="brief-byline"><span>${niEsc(primary.publisher_name)}</span><time datetime="${niEsc(item.published_at)}">${item.date_basis==='first_captured'?'Captured ':'Published '}${niEsc(date)}</time>${kind?`<span>${niEsc(kind)}</span>`:''}${freshnessLabel?`<span>${niEsc(freshnessLabel)}</span>`:''}<details><summary>Sources${item.sources.length>1?' ('+item.sources.length+')':''}</summary><div class="brief-source-info"><div class="muted">${niEsc(topic)} · ${niEsc(languageName(item.language))}<br>${item.date_basis==='first_captured'?'First captured':'Published'} ${niEsc(new Date(item.published_at).toLocaleString())} · ${item.report_count} report${item.report_count===1?'':'s'}</div><ul>${links}</ul></div></details></div></article>`;
}
function renderCoverage(data){
 el('briefCoverage').replaceChildren();
 const range=document.createElement('p');range.textContent=`${new Date(data.window_start).toLocaleString()} to ${new Date(data.window_end).toLocaleString()}`;
 const count=document.createElement('p');count.textContent=`${data.items.length} selected stories across ${data.selected_publisher_count||0} publishers${data.period==='weekly'?' and '+(data.selected_days||0)+' publication dates':''}. ${data.story_count} matching stories from ${data.publisher_count} publishers are available in the full stream. ${data.excluded_non_reports} non-news pages excluded; ${data.unavailable_summaries||0} stories lack enough readable text for the short brief. ${data.excluded_stale_or_uncertain||0} historical, expired or undated stories remain in More headlines.`;
 const capture=document.createElement('p');capture.textContent=data.latest_capture_at?`Newest first capture among the reports checked: ${new Date(data.latest_capture_at).toLocaleString()}. This records when a report first entered the archive. Publisher delays can leave gaps in coverage.`:'No source captures were available in this period for the selected publishers and languages.';
 el('briefCoverage').append(range,count,capture);
 el('captureStatus').hidden=false;el('captureStatus').textContent=`${data.selected_publisher_count||0} publisher${data.selected_publisher_count===1?'':'s'} in your short brief · ${data.story_count} matching stories in More headlines`;
 const captureAge=data.latest_capture_at?(new Date(data.window_end)-new Date(data.latest_capture_at))/3600000:0;
 el('captureWarning').hidden=captureAge<6;
 el('captureWarning').textContent=captureAge>=6?`The newest capture checked is ${Math.floor(captureAge)} hours old. More recent coverage may be missing. Refreshing this brief reads the archive; publisher fetching runs separately.`:'';
 el('briefNotice').hidden=!data.sampled;
 if(data.sampled)el('briefNotice').textContent=`Based on ${data.scanned_reports.toLocaleString()} of ${data.eligible_reports.toLocaleString()} captured reports. Some matching coverage may be missing. Personalize by publisher or language to narrow the selection.`;
}
async function loadEdition(){
 const current=++sequence;if(controller)controller.abort();controller=new AbortController();edition=null;nextOffset=null;fullShown=new Set();fullBusy=false;
 el('briefRefreshNotice').hidden=true;
 el('keepReading').hidden=true;el('showFullBrief').disabled=true;el('showFullBrief').hidden=false;el('moreBrief').hidden=true;el('fullBriefItems').hidden=true;el('fullBriefItems').replaceChildren();el('briefNotice').hidden=true;el('captureWarning').hidden=true;
 el('refreshBrief').disabled=true;el('briefItems').setAttribute('aria-busy','true');el('briefItems').innerHTML='<div class="empty">Getting your news…</div>';el('briefStatus').textContent='Getting your news…';el('captureStatus').hidden=true;el('readTime').textContent='About 2 min';el('briefCoverage').textContent='Checking coverage…';
 const filtered=Object.values(applied).some(values=>Array.isArray(values)&&values.length);el('clearBrief').hidden=!filtered;
 try{
  const data=await niApi('/api/v1/digests/preview',{method:'POST',body:JSON.stringify({period,filters:applied}),signal:controller.signal});if(current!==sequence)return;
  edition=data;applied=data.filters;fullShown=new Set(data.items.map(item=>item.article_id));
  const allNonCurrent=data.story_count>0&&data.excluded_stale_or_uncertain===data.story_count;
  el('briefItems').innerHTML=data.items.length?data.items.map(item=>card(item)).join(''):`<div class="empty"><b>${allNonCurrent?'No current stories for this brief.':data.story_count?'No readable summaries yet.':data.eligible_reports?'No matching stories found.':'No captured reports in this period.'}</b><p>${allNonCurrent?'The captured matches are historical, expired or missing a reliable publication date. Open More headlines to inspect them, or try fewer filters.':data.story_count?'Open More headlines to read the available sources, or try Weekly.':data.eligible_reports?'Try fewer filters or Weekly. The available captured reports may not cover your interests yet.':'Try Weekly or clear your filters. News appears after publishers are captured; refreshing this brief does not fetch publishers.'}</p><button id="emptyReset" class="secondary" type="button">Show all news</button></div>`;
  if(!data.items.length)el('emptyReset').onclick=resetBrief;
  el('readTime').textContent=data.items.length?`~${Math.max(1,Math.ceil(data.estimated_read_seconds/60))} min · ${data.items.length} stories`:'No stories';
  const label=previewLabel||(el('streamSelect').value?el('streamSelect').selectedOptions[0].textContent:'');
  el('briefStatus').textContent=`${label?label+' · ':''}${period==='daily'?'Past 24 hours':'Past 7 days'} · As of ${new Date(data.window_end).toLocaleString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}`;
  renderCoverage(data);el('keepReading').hidden=data.story_count<=data.items.length;el('showFullBrief').disabled=false;el('showFullBrief').textContent='More headlines';el('fullBriefItems').style.setProperty('--start',data.items.length);
 }catch(error){
  if(current!==sequence||error.name==='AbortError')return;
  el('briefItems').innerHTML=`<div class="error-box"><b>Your brief couldn't load.</b><p>${niEsc(error.message)}</p><button id="retryBrief" type="button">Try again</button></div>`;el('retryBrief').onclick=loadEdition;el('briefStatus').textContent='Please try again';el('readTime').textContent='Unavailable';el('briefCoverage').textContent='Coverage is available when your brief loads.';
 }finally{if(current===sequence){el('refreshBrief').disabled=false;el('briefItems').setAttribute('aria-busy','false');}}
}
async function loadFull(){
 if(!edition||fullBusy)return;
 const current=sequence,snapshot=edition,offset=nextOffset||0;fullBusy=true;el('showFullBrief').disabled=true;el('moreBrief').disabled=true;
 const button=el('showFullBrief').hidden?el('moreBrief'):el('showFullBrief');button.textContent='Loading…';
 try{
  const data=await niApi('/api/v1/digests/preview',{method:'POST',body:JSON.stringify({period:snapshot.period,filters:snapshot.filters,as_of:snapshot.window_end,full_stream:true,offset})});if(current!==sequence)return;
  const fresh=data.items.filter(item=>!fullShown.has(item.article_id));fresh.forEach(item=>fullShown.add(item.article_id));
  const list=el('fullBriefItems');list.hidden=false;list.insertAdjacentHTML('beforeend',fresh.map(item=>card(item,'h3')).join(''));
  nextOffset=data.next_offset;el('showFullBrief').hidden=true;el('moreBrief').hidden=nextOffset===null;el('moreBrief').textContent=`More headlines · ${fullShown.size} shown`;
 }catch(error){if(current===sequence)niToast('More headlines could not load. Please try again.','bad');}
 finally{if(current===sequence){fullBusy=false;el('showFullBrief').disabled=false;el('moreBrief').disabled=false;if(!el('showFullBrief').hidden)el('showFullBrief').textContent='More headlines';else if(nextOffset!==null)el('moreBrief').textContent=`More headlines · ${fullShown.size} shown`;}}
}
async function saveStream(update=false){
 if(streamBusy)return;
 const name=el('streamName').value.trim();if(!name){el('streamMessage').textContent='Give your feed a name first.';el('streamName').focus();return;}
 const id=update?el('streamSelect').value:'';if(update&&!id)return;lockStreams(true);el('streamMessage').textContent='Saving…';
 try{
  const saved=await niApi('/api/v1/digest-streams'+(id?'/'+encodeURIComponent(id):''),{method:id?'PUT':'POST',body:JSON.stringify({name,period,filters:filtersFromForm()})});
  streams=streams.filter(s=>s.id!==saved.id);streams.push(saved);populateStreams(saved.id);applied=saved.filters;previewLabel='';rememberChoices();el('streamMessage').textContent='Saved. Find it under My feeds.';niToast('Your feed is saved.');closeCustomize();await loadEdition();
 }catch(error){el('streamMessage').textContent='Could not save: '+error.message;}finally{lockStreams(false);}
}
function resetBrief(){
 setForm();el('streamName').value='';populateStreams();applied={};previewLabel='';el('streamMessage').textContent='';
 for(const id of ['publisherSearch','languageSearch'])el(id).value='';searchChoices('briefPublishers','');searchChoices('briefLanguages','');rememberChoices();loadEdition();
}
el('customizeBrief').onclick=()=>{if(!el('briefCustomize').hidden){closeCustomize();return;}el('briefCustomize').hidden=false;el('customizeBrief').setAttribute('aria-expanded','true');};
el('closeCustomize').onclick=closeCustomize;
el('briefCustomize').addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();closeCustomize();}});
el('briefTopics').addEventListener('change',syncTopics);
el('allTopics').onclick=()=>{el('briefTopics').querySelectorAll('input').forEach(input=>input.checked=false);syncTopics();};
el('publisherSearch').oninput=()=>searchChoices('briefPublishers',el('publisherSearch').value);
el('languageSearch').oninput=()=>searchChoices('briefLanguages',el('languageSearch').value);
for(const p of ['daily','weekly'])el(p+'Brief').onclick=()=>{setPeriod(p);rememberChoices();loadEdition();};
el('refreshBrief').onclick=()=>setupFailed?initialize():loadEdition();
el('applyBrief').onclick=()=>{applied=filtersFromForm();previewLabel='My choices';rememberChoices();closeCustomize();loadEdition();};
el('clearBrief').onclick=resetBrief;el('resetBrief').onclick=resetBrief;
el('streamSelect').onchange=()=>{const stream=streams.find(s=>s.id===el('streamSelect').value);applied=stream?stream.filters:{};previewLabel='';setForm(applied);el('streamName').value=stream?stream.name:'';if(stream)setPeriod(stream.period);populateStreams(stream?stream.id:'');rememberChoices();el('streamMessage').textContent='';closeCustomize();loadEdition();};
el('saveBrief').onclick=()=>saveStream();el('updateBrief').onclick=()=>saveStream(true);
el('deleteBrief').onclick=async()=>{
 const id=el('streamSelect').value;if(!id||streamBusy)return;lockStreams(true);
 try{await niApi('/api/v1/digest-streams/'+encodeURIComponent(id),{method:'DELETE'});streams=streams.filter(s=>s.id!==id);resetBrief();el('streamMessage').textContent='Feed deleted.';niToast('Feed deleted.');}
 catch(error){el('streamMessage').textContent='Could not delete: '+error.message;}finally{lockStreams(false);}
};
el('showFullBrief').onclick=loadFull;el('moreBrief').onclick=loadFull;
el('refreshStaleBrief').onclick=()=>setupFailed?initialize():loadEdition();
document.addEventListener('visibilitychange',checkSnapshotOnReturn);
window.addEventListener('pageshow',checkSnapshotOnReturn);
setInterval(()=>{if(document.visibilityState==='visible')updateSnapshotNotice();},60000);
async function initialize(){
 setupFailed=false;
 const setup=await Promise.allSettled([niApi('/api/v1/digests/options'),niApi('/api/v1/digest-streams'),niApi('/api/v1/digests/preferences')]);
 setupFailed=setup.some(result=>result.status==='rejected');
 if(setup[0].status==='fulfilled'){
  options=setup[0].value;
  el('briefTopics').innerHTML=options.topics.map(t=>`<label><input type="checkbox" value="${niEsc(t.key)}">${niEsc(t.label)}</label>`).join('');
  el('briefPublishers').innerHTML=options.publishers.map(p=>choice(p.id,p.name)).join('');
  el('briefLanguages').innerHTML=options.languages.map(code=>({code,name:languageName(code)})).sort((a,b)=>a.name.localeCompare(b.name)).map(language=>choice(language.code,language.name)).join('');
  setForm(applied);el('customizeBrief').disabled=false;
 }else niToast('Personalization could not load. Use Refresh to retry. You can still read all news.','bad');
 if(setup[1].status==='fulfilled'){streams=setup[1].value;populateStreams(el('streamSelect').value);}else niToast('Saved feeds could not load. Use Refresh to retry.','bad');
 if(setup[2].status==='fulfilled'&&!preferencesRestored){
  const prefs=setup[2].value;setPeriod(prefs.period);applied=prefs.filters;previewLabel='';
  if(setup[1].status==='fulfilled'){
   const selected=streams.find(stream=>stream.id===prefs.stream_id);
   populateStreams(selected?selected.id:'');el('streamName').value=selected?selected.name:'';
  }
  if(!prefs.stream_id&&Object.values(applied).some(values=>values.length))previewLabel='My choices';
  if(setup[0].status==='fulfilled')setForm(applied);preferencesRestored=true;
 }else if(setup[2].status==='rejected')niToast('Your last reading choices could not load. Use Refresh to retry.','bad');
 await loadEdition();
}
initialize();
"""


@router.get("/briefs", response_class=HTMLResponse)
async def digest_dashboard(auth: ViewerAuth) -> str:
    role = getattr(getattr(auth, "role", None), "value", "viewer")
    return render_app_page(title="Daily & weekly brief", body=BODY, active="briefs", role=role,
                           reader_mode=True,
                           scripts="<script>" + COMMON_JS + SCRIPT + "</script>")
