"""Exercise real FastAPI HTML/routes and browser scripts against an explicitly mocked DB source replay."""
import sys
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'qa' / 'results'
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0,str(ROOT/'qa'))
from replay_server import app, REPLAY_EVENTS, REPLAY_ARTICLES, REPLAY_BRIEF, EVENT_B
MOCKS = {
 '/api/v1/events?limit=40':REPLAY_EVENTS,
 '/api/v1/articles?limit=100':REPLAY_ARTICLES,
 '/api/v1/workspace/overview':{'counts':{'active_investigations':0,'watchlists':0,'saved_searches':0,'unacknowledged_alerts':0}},
 f'/api/v1/events/{EVENT_B}/briefing':REPLAY_BRIEF,
}
with TestClient(app) as client:
    pages={route:client.get(route) for route in ['/app','/news',f'/events/{EVENT_B}/briefing']}

def open_app_page(page,path):
    response=pages[path]
    assert response.status_code==200,(path,response.text[:150])
    # Because browser network is unavailable, feed the actual ASGI response into Chromium.
    # Only API responses are supplied by a strictly labeled, read-only source replay.
    mocks=json.dumps(MOCKS)
    preface='<script>window.fetch=async (url,options)=>{const raw=String(url);const db='+mocks+';const key=Object.keys(db).find(k=>raw.includes(k)); if(key)return new Response(JSON.stringify(db[key]),{status:200,headers:{"content-type":"application/json"}});return new Response(JSON.stringify({detail:"Not present in QA replay"}),{status:404,headers:{"content-type":"application/json"}});};</script>'
    page.set_content(response.text.replace('<script>',preface+'<script>',1),wait_until='domcontentloaded')
    return response

checks=[]; errors=[]; warnings=[]

def check(name,expr):
    ok=bool(expr);checks.append({'check':name,'ok':ok});print(('PASS' if ok else 'FAIL'),name)
    if not ok: raise AssertionError(name)

def screenshot(page,name):
    # QA replay label is browser-only; does not change the application.
    page.evaluate('''() => {if(!document.querySelector('#qaReplayBanner')){const b=document.createElement('aside');b.id='qaReplayBanner';b.style.cssText='position:sticky;top:64px;z-index:70;padding:9px 14px;background:#fef3c7;color:#713f12;text-align:center;font:700 13px sans-serif;border-bottom:1px solid #f59e0b';b.textContent='QA SOURCE REPLAY — public-source facts reconstructed locally; NOT live ingestion or worker-generated analysis';document.querySelector('.app-header')?.after(b)}}''')
    target=OUT / (name+'.png');page.screenshot(path=str(target),full_page=True);return str(target)

try:
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        for name,viewport in [('desktop',{'width':1440,'height':900}),('mobile',{'width':390,'height':844})]:
            context=browser.new_context(viewport=viewport,device_scale_factor=1,color_scheme='light',locale='en-IN')
            page=context.new_page()
            page.on('pageerror',lambda exc:errors.append(str(exc)))
            page.on('console',lambda msg: warnings.append(msg.text) if msg.type=='error' else None)
            response=open_app_page(page,'/app')
            check(name+' home HTTP 200',response.status_code==200)
            page.locator('#cReports').wait_for(state='attached')
            page.wait_for_function("document.getElementById('cReports').textContent==='3'",timeout=5000)
            check(name+' home captured report count',page.locator('#cReports').inner_text()=='3')
            check(name+' home contains PIB GatiShakti',page.get_by_text('Five years of PM GatiShakti infrastructure planning').count()>0)
            if name=='desktop':
                check('desktop sidebar visible',page.locator('.app-sidebar').is_visible())
                screenshot(page,'qa-home-desktop')
                page.locator('#themeToggle').click()
                check('theme switch to dark',page.locator('html').get_attribute('data-theme')=='dark')
                page.locator('#themeToggle').click()
            else:
                check('mobile no overflow',page.evaluate('document.documentElement.scrollWidth-document.documentElement.clientWidth')<6)
                check('mobile menu accessible',page.locator('#openMobileMenu').is_visible())
                page.locator('#openMobileMenu').click()
                check('mobile drawer open',page.locator('#mobileMenu').get_attribute('aria-hidden')=='false')
                page.keyboard.press('Escape')
                check('mobile drawer closes on Escape',page.locator('#mobileMenu').get_attribute('aria-hidden')=='true')
                screenshot(page,'qa-home-mobile')
            open_app_page(page,'/news')
            page.wait_for_function("document.getElementById('resultCount').textContent.includes('3 of 3')",timeout=5000)
            check(name+' news three source records',page.locator('.story-card').count()==3)
            check(name+' no useless older-page button',not page.locator('#loadMoreBtn').is_visible())
            check(name+' no duplicate status text',page.locator('.story-card .story-side .pattern').count()==0)
            check(name+' news displays real PIB headline',page.get_by_text('MCL expands electronic-waste collection').count()>0)
            page.locator('#search').fill('GatiShakti')
            page.wait_for_timeout(250)
            check(name+' news filter one result',page.locator('.story-card').count()==1)
            page.locator('#search').fill('')
            page.wait_for_timeout(250)
            page.locator('button[data-filter="material_update"]').click()
            check(name+' material-update filter one result',page.locator('.story-card').count()==1)
            page.locator('button[data-filter="all"]').click()
            screenshot(page,'qa-news-'+name)
            if name=='desktop':
                open_app_page(page,f'/events/{EVENT_B}/briefing')
                page.get_by_text('Five years of PM GatiShakti infrastructure planning').first.wait_for(timeout=5000)
                check('briefing source links visible',page.locator('.source-ref').count()>0)
                check('briefing source panel citations',page.locator('.reference-card').count()==3)
                check('briefing shows qualified language', 'not independent verification' in page.locator('#whatHappened').inner_text())
                page.locator('.source-ref').first.click()
                check('briefing anchor navigation',page.url.endswith('#source-reference-1'))
                screenshot(page,'qa-briefing-desktop')
            context.close()
        browser.close()
finally:
    pass
report={'checks':checks,'passed':sum(x['ok'] for x in checks),'failed':sum(not x['ok'] for x in checks),'browser_errors':errors,'console_errors':warnings,'source_type':'EXTERNAL-PUBLIC-SOURCE-REPLAY-LOCAL-FIXTURE','live_crawler_tested':False,'postgresql_tested':False,'screenshots':sorted(str(x.name) for x in OUT.glob('*.png'))}
(OUT/'browser_report.json').write_text(json.dumps(report,indent=2))
print('RESULT:',json.dumps(report,indent=2))
if report['failed'] or errors: sys.exit(1)
