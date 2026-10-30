"""Execute the shipped reader script with a controlled clock and DOM state."""
import json
import re
import subprocess
from pathlib import Path

from newsintel.api.routes.digest_dashboard import BODY, SCRIPT

HARNESS = r"""
const vm=require('node:vm'),assert=require('node:assert/strict');
const source=require('node:fs').readFileSync(0,'utf8').replace(/\ninitialize\(\);\s*$/,'');
const nodes=new Map(),events={},timers=[];
const node=id=>{if(!nodes.has(id))nodes.set(id,{hidden:true,value:'',textContent:'',disabled:false,
 classList:{toggle(){}},setAttribute(){},addEventListener(){},replaceChildren(){},add(){},focus(){},
 querySelectorAll(){return []}});return nodes.get(id)};
let now=Date.parse('2026-10-30T12:00:00Z');
class ClockDate extends Date{constructor(...args){super(...(args.length?args:[now]))}static now(){return now}}
const document={getElementById:node,visibilityState:'visible',addEventListener:(name,fn)=>events[name]=fn};
const context=vm.createContext({document,window:{addEventListener:(name,fn)=>events[name]=fn},
 setInterval:fn=>timers.push(fn),Date:ClockDate,Option:function(){},Intl,navigator:{language:'en'},
 niEsc:String,niSafeUrl:String,niToast(){},loads:0});
vm.runInContext(source,context);
vm.runInContext("loadEdition=()=>{loads++};edition={window_end:'2026-10-30T12:00:00Z'}",context);
timers[0]();assert.equal(node('briefRefreshNotice').hidden,true);
now+=6*60*1000;timers[0]();assert.equal(node('briefRefreshNotice').hidden,false);
assert.equal(context.loads,0,'timer must not discard reading position');
document.visibilityState='hidden';events.visibilitychange();assert.equal(context.loads,0);
document.visibilityState='visible';node('briefCustomize').hidden=false;
events.visibilitychange();assert.equal(context.loads,0,'preserve unsaved personalization');
node('briefCustomize').hidden=true;node('fullBriefItems').hidden=false;
events.pageshow();assert.equal(context.loads,0,'preserve longer-stream reading');
node('fullBriefItems').hidden=true;events.visibilitychange();assert.equal(context.loads,1);
node('refreshStaleBrief').onclick();assert.equal(context.loads,2);
vm.runInContext("streams=[{id:'saved',name:'Morning science',filters:{}}];populateStreams('saved')",context);
assert.equal(node('streamName').value,'Morning science','restored feed must be editable');
const html=vm.runInContext(`card({article_id:'test',title:'Headline',explanation:'Excerpt',
 sources:[{publisher_name:'Publisher',article_id:'test',url:'https://example.com/report'}],
 topic:'general',language:'en',published_at:'2026-10-30T10:00:00Z',date_basis:'first_captured',
 freshness_status:'date_unconfirmed',freshness_reason:'Original publication date unknown.',report_count:1})`,context);
assert.match(html,/Publication date unconfirmed/);assert.match(html,/Captured /);assert.match(html,/2026/);
console.log(JSON.stringify({timer_prompt:true,return_refresh:true,editing_preserved:true,
 reading_preserved:true,saved_feed_name:true,full_publication_time:true,uncertain_date_label:true}));
"""


if __name__ == "__main__":
    ids = set(re.findall(r'id="([^"]+)"', BODY))
    assert set(re.findall(r"el\('([^']+)'\)", SCRIPT)) - {"emptyReset", "retryBrief"} <= ids
    result = subprocess.run(["node", "-e", HARNESS], input=SCRIPT, capture_output=True,
                            text=True, encoding="utf-8", timeout=15, check=True)
    evidence = json.loads(result.stdout)
    output = Path(__file__).resolve().parents[1] / ".run/audit/brief-lifecycle-20261030.json"
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(result.stdout.strip())
