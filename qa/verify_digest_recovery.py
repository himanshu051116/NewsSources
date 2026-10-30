"""Exercise actual brief setup/Refresh handlers after transient request failures."""
import json
import subprocess
from pathlib import Path

from newsintel.api.routes.digest_dashboard import SCRIPT

HARNESS = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = require('node:fs').readFileSync(0, 'utf8');
assert.match(source, /\ninitialize\(\);\s*$/);
const script = source.replace(/\ninitialize\(\);\s*$/, '');
async function scenario(failOptions) {
  const nodes = new Map();
  const calls = {options:0, streams:0};
  const writes = [];
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {
      value:'', disabled:id==='customizeBrief', hidden:true,
      classList:{toggle(){}}, setAttribute(){}, addEventListener(){},
      querySelectorAll(){return []}, replaceChildren(){}, add(){}, focus(){}
    });
    return nodes.get(id);
  };
  const context = vm.createContext({
    document:{getElementById:node,addEventListener(){},visibilityState:'visible'},
    window:{addEventListener(){}},setInterval(){},
    Option:function(text,value){this.text=text;this.value=value},
    niEsc:String, niToast(){}, editionLoads:0,
    niApi:async (route, request={}) => {
      if (route.endsWith('/preferences')) {
        if (request.method==='PUT') {writes.push(JSON.parse(request.body));return writes.at(-1)}
        return {period:'weekly',filters:{keywords:['climate']},stream_id:null};
      }
      if (route.endsWith('/options')) {
        calls.options++;
        if (failOptions && calls.options===1) throw Error('temporary database timeout');
        return {topics:[],publishers:[],languages:[]};
      }
      if (route.endsWith('/digest-streams')) {
        calls.streams++;
        if (calls.streams===1) throw Error('temporary database timeout');
        return [{id:'existing-feed',name:'Existing feed',filters:{},period:'daily'}];
      }
      throw Error('Unexpected API request '+route);
    }
  });
  vm.runInContext(script, context);
  // Edition loading is independent; execute the real setup and click handlers.
  vm.runInContext('loadEdition=async()=>{editionLoads++}', context);
  await vm.runInContext('initialize()', context);
  assert.equal(vm.runInContext('period',context),'weekly');
  assert.equal(vm.runInContext('applied.keywords[0]',context),'climate');
  assert.equal(node('customizeBrief').disabled, failOptions);
  node('streamSelect').value='existing-feed';
  await node('refreshBrief').onclick();
  assert.equal(node('customizeBrief').disabled,false);
  assert.equal(node('streamSelect').value,'existing-feed');
  assert.deepEqual(calls,{options:2,streams:2});
  await node('refreshBrief').onclick();
  assert.deepEqual(calls,{options:2,streams:2});
  assert.equal(context.editionLoads,3);
  vm.runInContext("period='daily';applied={topics:['sports']};rememberChoices();period='weekly';applied={topics:['science_health']};rememberChoices()",context);
  await vm.runInContext('preferenceWrites',context);
  assert.deepEqual(writes.map(p=>[p.period,p.filters.topics[0]]),[['daily','sports'],['weekly','science_health']]);
  return {scenario:failOptions?'options and feeds fail':'feeds fail',recovered:true};
}
(async()=>console.log(JSON.stringify(await Promise.all([scenario(true),scenario(false)]))))()
  .catch(error=>{console.error(error);process.exitCode=1});
"""


if __name__ == "__main__":
    result = subprocess.run(["node", "-e", HARNESS], input=SCRIPT, capture_output=True,
                            text=True, encoding="utf-8", timeout=15, check=True)
    evidence = json.loads(result.stdout)
    path = Path(__file__).resolve().parents[1] / ".run/audit/digest-recovery-check-20261028.json"
    path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print("Passed: setup recovers; reading choices restore; selection survives; preference writes stay ordered.")
