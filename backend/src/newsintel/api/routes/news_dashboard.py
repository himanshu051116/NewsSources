# ruff: noqa: E501
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from newsintel.api.dependencies import ViewerAuth
from newsintel.api.ui import COMMON_JS, render_app_page

router = APIRouter(tags=["news-dashboard"])

BODY = r"""
<style>
.news-head h1{font-size:36px;margin:0}.news-head .lead{font-size:15px}.news-controls{display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin-bottom:20px}.news-controls label{display:grid;gap:6px;font-size:12px;font-weight:650}.news-controls label:first-child{flex:1;min-width:180px}.news-controls label:last-child{min-width:155px}.news-meta{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:16px;font-size:12px;color:var(--muted)}.news-card{padding:24px 0;border-top:1px solid var(--line)}.news-card h2{font-size:21px;line-height:1.4;letter-spacing:-.02em;margin:8px 0}.news-card h2 a{color:var(--text);overflow-wrap:anywhere}.news-card p{font-size:15px;line-height:1.7;color:var(--muted);margin:8px 0 12px}.news-byline{display:flex;gap:10px;flex-wrap:wrap;font-size:12px;color:var(--muted)}.news-source{color:var(--brand);font-size:12px;font-weight:700}.news-card details{font-size:12px}.news-card summary{cursor:pointer;min-height:32px;color:var(--brand);display:flex;align-items:center}.news-card ul{line-height:1.9}.news-end{text-align:center;margin:24px 0}.news-note{font-size:12px;color:var(--muted);line-height:1.7}.news-loading{min-height:180px}.news-controls input{min-height:44px}
@media(max-width:520px){.news-head{flex-direction:row;gap:12px}.news-head h1{font-size:30px}.news-head .lead{font-size:14px}.news-meta{align-items:flex-start;flex-direction:column}.news-controls label:last-child{flex:1}.news-card h2{font-size:19px}.news-card{padding:20px 0}}
</style>
<header class="page-head news-head"><div><h1>Latest news</h1><p class="lead">Recent reporting from connected publishers.<br>Publication dates checked. Original sources linked.</p></div><button id="refreshNews" class="secondary" type="button">Update</button></header>
<section class="panel news-controls" aria-label="Find recent news">
 <label for="newsSearch">Find a headline<input id="newsSearch" type="search" placeholder="Search headlines already loaded…" autocomplete="off"></label>
 <label for="newsPeriod">Published in<select id="newsPeriod"><option value="daily">Past 24 hours</option><option value="weekly">Past 7 days</option></select></label>
</section>
<div class="news-meta"><span id="newsStatus" role="status" aria-live="polite">Getting the latest reporting…</span><a href="/briefs">Just the highlights? Read your brief →</a></div>
<div id="newsRefreshNotice" class="notice" hidden style="margin-bottom:16px" role="status">This view is more than five minutes old. <button id="updateStaleNews" class="secondary" type="button">Check latest news</button></div>
<div id="newsWarning" class="notice warn" hidden></div>
<section id="newsItems" aria-label="Recent headlines" aria-live="polite"><div class="empty news-loading">Getting the latest reporting…</div></section>
<div class="news-end"><button id="moreNews" class="secondary" type="button" hidden>More headlines</button></div>
<p class="news-note">This view includes reports with a publisher publication date in the selected period. Undated captures, archive reprints and clearly expired live sessions are excluded. <a href="/search">Search the archive</a> for older reporting.</p>
"""

SCRIPT = r"""
const el=id=>document.getElementById(id);
let articles=[],snapshot=null,nextOffset=null,sequence=0,busy=false,controller=null;
function renderNews(){
 const query=el('newsSearch').value.trim().toLocaleLowerCase();
 const rows=articles.filter(item=>(item.title+' '+item.explanation+' '+item.sources.map(s=>s.publisher_name).join(' ')).toLocaleLowerCase().includes(query));
 el('newsItems').innerHTML=rows.length?rows.map(item=>{
  const source=item.sources[0],kind={analysis:'Analysis',opinion:'Opinion',service:'Lifestyle & service'}[item.report_type]||'';
  const link=source.url?niSafeUrl(source.url):`/articles/${niEsc(item.article_id)}/intelligence`;
  return `<article class="news-card"><div class="news-source">${niEsc(source.publisher_name)}${kind?' · '+niEsc(kind):''}</div><h2><a href="${niEsc(link)}"${source.url?' target="_blank" rel="noopener noreferrer"':''}>${niEsc(item.title)}</a></h2>${item.summary_available?`<p>${niEsc(item.explanation)}</p>`:''}<div class="news-byline"><time datetime="${niEsc(item.published_at)}">Published ${niEsc(new Date(item.published_at).toLocaleString([],{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}))}</time><a href="/articles/${niEsc(item.article_id)}/intelligence">Saved report</a></div>${item.sources.length>1?`<details><summary>${item.sources.length} publishers covering this story</summary><ul>${item.sources.map(s=>`<li><a href="${niEsc(s.url?niSafeUrl(s.url):'/articles/'+s.article_id+'/intelligence')}" target="_blank" rel="noopener noreferrer">${niEsc(s.publisher_name)}</a></li>`).join('')}</ul></details>`:''}</article>`;
 }).join(''):`<div class="empty"><b>${articles.length?'No loaded headlines match.':'No current reporting in this period.'}</b><p>${articles.length?'Try another word, or load more headlines.':'Try Past 7 days. Publisher fetching runs separately; Update checks the captured archive.'}</p></div>`;
 el('moreNews').hidden=nextOffset===null;
 if(snapshot)el('newsStatus').textContent=`${rows.length} of ${articles.length} loaded · As of ${new Date(snapshot.window_end).toLocaleString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}`;
}
async function loadNews(more=false){
 if(more&&(busy||!snapshot||nextOffset===null))return;
 const token=++sequence;if(controller)controller.abort();controller=new AbortController();busy=true;
 el('refreshNews').disabled=true;el('moreNews').disabled=true;el('newsItems').setAttribute('aria-busy','true');
 if(!more){articles=[];snapshot=null;nextOffset=null;el('moreNews').hidden=true;el('newsItems').innerHTML='<div class="empty news-loading">Getting the latest reporting…</div>';el('newsStatus').textContent='Getting the latest reporting…';el('newsWarning').hidden=true;el('newsRefreshNotice').hidden=true;}
 try{
  const data=await niApi('/api/v1/digests/preview',{method:'POST',body:JSON.stringify({period:more?snapshot.period:el('newsPeriod').value,full_stream:true,current_only:true,page_size:50,offset:more?nextOffset:0,...(more?{as_of:snapshot.window_end}:{})}),signal:controller.signal});
  if(token!==sequence)return;snapshot=data;nextOffset=data.next_offset;
  const known=new Set(articles.map(item=>item.article_id));articles.push(...data.items.filter(item=>!known.has(item.article_id)));renderNews();
  const age=data.latest_capture_at?(Date.now()-new Date(data.latest_capture_at).getTime())/3600000:0;
  el('newsWarning').hidden=!data.sampled&&age<6;
  el('newsWarning').textContent=age>=6?'The newest capture checked is more than six hours old. More recent coverage may be missing.':`This busy period checks a sample of ${data.scanned_reports.toLocaleString()} reports. Some coverage may be missing.`;
 }catch(error){
  if(token!==sequence||error.name==='AbortError')return;
  if(more)niToast('More headlines could not load. Try again.','bad');else{el('newsItems').innerHTML=`<div class="error-box"><b>News could not load.</b><p>${niEsc(error.message)}</p><button id="retryNews" type="button">Try again</button></div>`;el('retryNews').onclick=()=>loadNews();el('newsStatus').textContent='Please try again';}
 }finally{if(token===sequence){busy=false;el('refreshNews').disabled=false;el('moreNews').disabled=false;el('newsItems').setAttribute('aria-busy','false');}}
}
el('newsPeriod').onchange=()=>loadNews();el('refreshNews').onclick=()=>loadNews();el('moreNews').onclick=()=>loadNews(true);el('newsSearch').oninput=niDebounce(renderNews,120);
function newsIsStale(){return snapshot&&Date.now()-new Date(snapshot.window_end).getTime()>=5*60*1000;}
el('updateStaleNews').onclick=()=>loadNews();
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&newsIsStale()){el('newsRefreshNotice').hidden=false;if(!busy&&articles.length<=50&&!el('newsSearch').value.trim())loadNews();}});
setInterval(()=>{if(document.visibilityState==='visible')el('newsRefreshNotice').hidden=!newsIsStale();},60000);
loadNews();
"""


@router.get("/news", response_class=HTMLResponse)
async def news_dashboard(auth: ViewerAuth) -> str:
    role = getattr(getattr(auth, "role", None), "value", "viewer")
    return render_app_page(title="Latest news", body=BODY, active="news", role=role,
                           reader_mode=True, scripts="<script>" + COMMON_JS + SCRIPT + "</script>")
