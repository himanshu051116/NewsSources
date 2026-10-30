"""QA ONLY: serve the actual FastAPI UI with a transparent recorded-source API replay.

This bypasses PostgreSQL and live ingestion. It must not be used for production
or represented as a successful live crawl. Only read-only QA responses are supplied.
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from fastapi import Request
from fastapi.responses import JSONResponse

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'backend' / 'src'))

from newsintel.api.dependencies import get_current_user
from newsintel.application.auth.dto import CurrentUser
from newsintel.core.config import get_settings
from newsintel.domain.access import AccessRole, AccessStatus, permissions_for_role
from newsintel.main import create_app


def uid(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, 'newsintel-replay-2026-10-14:'+value))


NOW = '2026-10-14T00:00:00+00:00'
EVENT_A = uid('event-mcl')
EVENT_B = uid('event-gatishakti')
EVENT_C = uid('event-sebi')
ART_A = uid('mcl-pib')
ART_B = uid('pm-gati-pib')
ART_C = uid('sebi')
URL_A = 'https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2322767'
URL_B = 'https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2322825'
URL_C = 'https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListingAll=yes&sid=6&smid=0&ssid=0'

REPLAY_ARTICLES = [
    dict(id=ART_A,event_id=EVENT_A,title='MCL expands electronic-waste collection and reports first-week cleanup results',published_at='2026-10-13T10:15:00+00:00',first_observed_at=NOW,language='en',word_count=152,latest_extraction_fidelity_label='moderate',latest_extraction_warnings=['source_snapshot_replayed'],historical_context_status='internal_only',historical_depth='limited',historical_change_pattern='mostly_new_reporting',latest_extraction_quality_score=.71,canonical_url=URL_A),
    dict(id=ART_B,event_id=EVENT_B,title='PM GatiShakti completes five years; ministry describes platform expansion',published_at='2026-10-13T11:29:00+00:00',first_observed_at=NOW,language='en',word_count=204,latest_extraction_fidelity_label='moderate',latest_extraction_warnings=['source_snapshot_replayed'],historical_context_status='complete',historical_depth='moderate',historical_change_pattern='material_update',latest_extraction_quality_score=.71,canonical_url=URL_B),
    dict(id=ART_C,event_id=EVENT_C,title='SEBI publishes consultation paper on monitoring use of issue proceeds',published_at='2026-10-13T08:00:00+00:00',first_observed_at=NOW,language='en',word_count=None,latest_extraction_fidelity_label=None,latest_extraction_warnings=['listing_only_no_article_body'],historical_context_status='pending',historical_depth=None,historical_change_pattern=None,latest_extraction_quality_score=None,canonical_url=URL_C),
]
REPLAY_EVENTS = [
    dict(id=EVENT_B,title='Five years of PM GatiShakti infrastructure planning',article_count=1,publisher_count=1,last_material_change_at=NOW,lifecycle_status='developing',first_detected_at=NOW,slug='pm-gatishakti-five-years'),
    dict(id=EVENT_A,title='MCL electronic-waste management campaign',article_count=1,publisher_count=1,last_material_change_at=NOW,lifecycle_status='developing',first_detected_at=NOW,slug='mcl-ewaste'),
    dict(id=EVENT_C,title='SEBI consultation on issue proceeds monitoring',article_count=1,publisher_count=1,last_material_change_at=NOW,lifecycle_status='developing',first_detected_at=NOW,slug='sebi-consultation'),
]
REF_B = 'article_version:'+uid('pm-gati-version')
REF_H = 'historical_context:'+uid('pm-gati-original-2021')
REF_2025 = 'historical_context:'+uid('pm-gati-aug-2025')
URL_H = 'https://www.pib.gov.in/Pressreleaseshare.aspx?PRID=1763576&lang=2&reg=48'
URL_2025 = 'https://www.pib.gov.in/PressReleasePage.aspx?PRID=2152521&lang=2&reg=3'
REPLAY_BRIEF = dict(
    id=uid('briefing'),event_id=EVENT_B,trigger_article_version_id=uid('pm-gati-version'),generated_at=NOW,
    methodology_version='QA-source-replay-only',evidence_pack_sha256='qa-replay-not-generated-by-platform',
    payload=dict(
        event=dict(title='Five years of PM GatiShakti infrastructure planning',lifecycle_status='developing'),
        what_happened=dict(text='The Ministry of Commerce & Industry published a five-year update about PM GatiShakti on 13 October 2026. These figures are statements from the ministry, not independent verification.',evidence_ids=[REF_B]),
        what_changed=dict(text='The government reported 293 projects worth ₹13.59 lakh crore in August 2025, compared with more than 400 projects worth ₹20.23 lakh crore in its October 2026 bulletin. These are ministry-reported figures from different dates, not an independently audited change estimate.',evidence_ids=[REF_B,REF_2025]),
        why_it_matters=dict(text='The described expansion could affect infrastructure planning across departments; this is an interpretation, not a measured impact finding.',evidence_ids=[REF_B]),
        latest_reporting=[dict(title='PM GatiShakti National Master Plan completes five years',publisher='Press Information Bureau / Ministry of Commerce & Industry',published_at='2026-10-13T11:29:00+00:00',evidence_ids=[REF_B])],
        historical_background=[
            dict(title='Prime Minister launches PM GatiShakti National Master Plan',source='PIB launch release · 13 October 2021',published_at='2021-10-13T08:20:00+00:00',url=URL_H,ref=REF_H),
            dict(title='Government reports 293 projects worth ₹13.59 lakh crore reviewed',source='PIB progress release · 5 August 2025',published_at='2025-08-05T10:43:00+00:00',url=URL_2025,ref=REF_2025),
        ],
        established_facts=[], disputed_or_contradicted=[],
        unresolved_or_insufficient_evidence=[dict(text='The public release alone cannot independently establish how many projects were completed or their effects.',verification='not_checkable',evidence_link_count=0,evidence_ids=[REF_B])],
        corrections=[],methodology=dict(grounding_rule='QA-only source replay. Statements are paraphrases of a public ministry release, not output generated by the platform briefing worker.')
    ),
    evidence_refs=[dict(id=REF_B,title='PIB: PM GatiShakti five-year update, 13 October 2026',kind='article_version',url=URL_B),dict(id=REF_H,title='PIB: Original GatiShakti launch, 13 October 2021',kind='historical_context',url=URL_H),
                   dict(id=REF_2025,title='PIB: PM GatiShakti NPG project review, 5 August 2025',kind='historical_context',url=URL_2025)],
)

app = create_app()

@asynccontextmanager
async def replay_lifespan(application):
    application.state.settings = get_settings()
    yield

app.router.lifespan_context = replay_lifespan

user_now = datetime.now(UTC)
ROLE = AccessRole.ANALYST
CURRENT_USER = CurrentUser(
    id=uid('qa-user'),auth_provider='qa',auth_provider_user_id='qa-only',verified_email='analyst@qa.invalid',
    display_name='QA Analyst',avatar_url=None,access_status=AccessStatus.APPROVED,role=ROLE,
    requested_at=user_now,approved_at=user_now,rejected_at=None,rejection_reason=None,
    suspended_at=None,suspension_reason=None,revoked_at=None,revocation_reason=None,
    access_expires_at=None,last_login_at=user_now,last_activity_at=user_now,created_at=user_now,updated_at=user_now,
    permissions=frozenset(p.value for p in permissions_for_role(ROLE)),credential_source='qa-replay',
)

async def qa_user():
    return CURRENT_USER
app.dependency_overrides[get_current_user] = qa_user

@app.middleware('http')
async def qa_recorded_source_api(request: Request, call_next):
    path=request.url.path
    if request.method != 'GET':
        if path.startswith('/api/'):
            return JSONResponse({'detail':'Write operations are disabled in the read-only source replay'},status_code=405)
        return await call_next(request)
    if path == '/api/v1/events' and request.query_params.get('limit'):
        return JSONResponse(REPLAY_EVENTS)
    if path == '/api/v1/articles':
        offset=int(request.query_params.get('offset','0'))
        limit=int(request.query_params.get('limit','100'))
        return JSONResponse(REPLAY_ARTICLES[offset:offset+limit])
    if path == f'/api/v1/events/{EVENT_B}/briefing':
        return JSONResponse(REPLAY_BRIEF)
    if path == '/api/v1/workspace/overview':
        return JSONResponse({'counts':{'active_investigations':0,'watchlists':0,'saved_searches':0,'unacknowledged_alerts':0}})
    return await call_next(request)

if __name__ == '__main__':
    import uvicorn
    print('QA REPLAY ONLY: The browser displays externally sourced, manually reconstructed records. Live ingestion, database, historical worker and briefing generation are NOT running.')
    uvicorn.run(app,host='127.0.0.1',port=int(os.getenv('NI_QA_PORT','8885')),access_log=False)
