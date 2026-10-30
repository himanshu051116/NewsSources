"""Run the genuine extraction + candidate-claim engine on shortened source-derived HTML.

Data were manually reconstructed from independently retrieved official release listings.
NOT a test of network fetch, RSS discovery, event DB writes, evidence verification, or workers.
"""
from __future__ import annotations
import json
import sys
from datetime import UTC, datetime
from html import escape
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'/'src'))
from newsintel.adapters.extractors.article_html import extract_article_html
from newsintel.domain.intelligence.claims import extract_claims

cases=[
 dict(
  publisher='PIB / Ministry of Coal',
  title='MCL strengthens electronic-waste management during Special Campaign 6',
  url='https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2322767',
  published='2026-10-13T15:45:00+05:30',
  text='Mahanadi Coalfields Limited reported that it cleaned 73 of 240 designated sites during the first week of Special Campaign 6. The organisation reported an area of 306663 square feet cleaned towards a 1000000 square foot target. Its ministry bulletin says 350 machinery batteries were disposed of during the drive. The ministry describes authorised collection channels for used electronics and a campaign planned to continue to 31 October 2026.'
 ),
 dict(
  publisher='PIB / Ministry of Commerce & Industry',
  title='PM GatiShakti completes five years and ministry describes planning expansion',
  url='https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2322825',
  published='2026-10-13T16:59:00+05:30',
  text='The Ministry of Commerce and Industry says the PM GatiShakti National Master Plan was launched in October 2021. The ministry says the platform now includes more than 1800 data layers across 58 central ministries and departments and all 36 states and union territories. It reports that the Network Planning Group evaluated more than 400 infrastructure projects worth about 20.23 lakh crore rupees. The ministry says the platform reached district-level and social-sector planning, while a public interface was introduced in September 2025.'
 )
]
results=[]
for c in cases:
 html=f'''<!doctype html><html lang="en"><head><title>{escape(c['title'])}</title>
 <link rel="canonical" href="{escape(c['url'])}"><meta property="article:published_time" content="{c['published']}">
 <meta property="og:title" content="{escape(c['title'])}"></head><body>
 <nav>Home News Sign in</nav><article><h1>{escape(c['title'])}</h1><p>{escape(c['text'])}</p></article>
 <footer>Subscribe now</footer></body></html>'''
 parsed=extract_article_html(html.encode('utf-8'),base_url=c['url'])
 claims=extract_claims(parsed.text_content)
 assert parsed.title==c['title']
 assert parsed.canonical_url==c['url']
 assert parsed.published_at is not None
 assert parsed.text_content == c['text'], (parsed.text_content,c['text'])
 assert len(claims)>=3
 results.append({
   'publisher':c['publisher'],'source_url':c['url'],'article_title':parsed.title,
   'published_at':parsed.published_at.isoformat(),'extraction_method':parsed.extraction_method,
   'extracted_words':parsed.word_count,'warnings':list(parsed.warnings),
   'claim_candidate_count':len(claims),'candidate_claims':[x.text for x in claims],
   'verified_claim_count':0,
   'verification_label':'UNVERIFIED — claims are candidate propositions extracted from a paraphrased QA source snapshot',
   'full_live_html_fetched':False,
 })
out=ROOT/'qa'/'results'/'source_replay_report.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'run_at':datetime.now(UTC).isoformat(),'source_method':'Official releases independently retrieved via web, rephrased and locally reconstructed as short HTML','live_network_fetch':False,'records':results},indent=2,ensure_ascii=False))
print(json.dumps({'records':len(results),'total_candidate_claims':sum(x['claim_candidate_count'] for x in results),'extraction_warning_counts':[len(x['warnings']) for x in results],'output':str(out)},indent=2))
