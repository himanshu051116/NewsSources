from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from newsintel.api.dependencies import get_current_user
from newsintel.api.routes.digests import get_digest_service
from newsintel.application.digests import (
    WORD_BUDGET,
    DigestFilters,
    DigestRequest,
    ReadingPreferences,
    SavedStream,
    StreamInput,
    group_reports,
    is_reporting_page,
    item_words,
    news_topic,
    short_edition,
    source_line,
    word_count,
)
from newsintel.domain.access import AccessRole, AccessStatus, permissions_for_role
from newsintel.main import create_app

NOW = datetime(2026, 10, 23, 12, tzinfo=UTC)


def report(**changes):
    article_id = uuid4()
    return dict(article_id=article_id, event_id=uuid4(), publisher_id=uuid4(),
                publisher_name="Example news", url="https://news.example/report",
                title="Central bank announces a new interest rate policy",
                text="Officials said the central bank would cut interest rates by 0.25 percent.",
                content_hash=article_id.hex * 2, language="en", published_at=NOW,
                date_basis="published", **changes)


def test_source_excerpt_preserves_qualification_attribution_and_numbers():
    sentence = "Officials said at least 12 people may have been affected by the outage."
    assert source_line("Advertisement\n" + sentence + " More reporting follows.",
                       "Outage") == sentence
    assert source_line("", "Headline") == (
        "Source text unavailable. Open the original report for details."
    )


def test_excerpt_skips_repeated_headline_and_marks_truncation():
    headline = "The government announces a major national infrastructure expansion"
    lead = ("According to the ministry, planned infrastructure improvements will connect remote "
            "villages with district hospitals, regional schools, major railway stations and "
            "industrial centres through a national network of new roads and bridges, supporting "
            "businesses across several states during the next construction phase.")
    excerpt = source_line(headline + "\n" + lead, headline)
    assert excerpt.startswith("According to the ministry,")
    assert excerpt.endswith("…")
    assert word_count(excerpt) <= 30
    assert len(excerpt) <= 241


def test_caption_repetition_and_historical_context_do_not_become_current_summaries():
    title = "Farmers fear losses as Cyclone Arnab floods paddy fields"
    caption = "Cyclone Arnab floods thousands of acres of paddy fields in Srikakulam"
    assert source_line("jKlWpoQt " + caption + " " + caption + ".", title) == (
        "Source text unavailable. Open the original report for details.")
    title = "Infant deaths renew calls for a health-care review"
    historical = "Another infant death was reported from the tribal area on February 28, 2017."
    current = "Officials announced a new health-care review after the latest infant deaths."
    assert source_line(historical+"\n"+current, title, 2026) == current
    assert source_line("Internal player metadata and a caption without a complete sentence", title) == (
        "Source text unavailable. Open the original report for details.")


def test_crime_reports_do_not_enter_health_or_finance_from_incidental_body_terms():
    assert news_topic("Police investigate death of a social media influencer",
                      "He provided financial advice about investment and revenue.") == "law_justice"
    assert news_topic("Man arrested for assault", "Doctors took him to hospital.") == "law_justice"


def test_prepared_version_excerpt_matches_live_analysis_without_repeating_it(monkeypatch):
    from newsintel.domain.intelligence.digest_quality import prepare_excerpt

    row = report()
    expected = group_reports([row], DigestFilters())
    row["prepared_excerpt"] = prepare_excerpt(row["text"], row["title"], NOW.year)

    def unexpected(*args):
        raise AssertionError("Prepared versions must not repeat sentence analysis")

    monkeypatch.setattr("newsintel.application.digests.source_line", unexpected)
    assert group_reports([row], DigestFilters()) == expected


def test_bilingual_announcement_uses_one_short_slot_without_losing_full_reports():
    english, hindi, different = report(), report(), report()
    english.update(title="Cabinet approves 3% dearness allowance hike for central government employees",
                   text="The cabinet approved a 3 percentage point dearness allowance increase for central government employees.")
    hindi.update(title="केंद्र सरकार के कर्मचारियों के महंगाई भत्ते में बढ़ोतरी को मंजूरी",
                 text="केंद्र सरकार के कर्मचारियों के लिए महंगाई भत्ते में 3 फीसदी बढ़ोतरी की मंजूरी दी गई है.",
                 language="hi")
    different.update(title="Cabinet approves 4% dearness allowance hike for central government employees",
                     text="The cabinet approved a 4 percentage point dearness allowance increase for central government employees.")
    stories = group_reports([english, hindi, different], DigestFilters())
    assert len(stories) == 3
    chosen = short_edition(stories, as_of=NOW)
    assert len(chosen) == 2
    assert different["article_id"] in {item.article_id for item in chosen}


def test_multilingual_reading_budget_does_not_treat_cjk_as_one_word():
    assert word_count("新闻" * 50) == 100
    assert news_topic("आज क्रिकेट टीम की जीत हुई") == "sports"
    assert news_topic("University students will take the final exam") == "education"
    assert news_topic("Leopard found dead on farmland", "An investigation team is on site") == (
        "climate_environment"
    )
    assert news_topic("आज का राशिफल: व्यापार में बढ़त") == "lifestyle"
    assert news_topic("तिब्बत में भूकंप के तेज झटके") == "climate_environment"
    assert news_topic("Aaj ka Meen Rashifal: व्यापार में लाभ") == "lifestyle"
    assert news_topic(
        "Why Moorthy is our spirit animal", "Related stories about AI apps",
        "https://news.example/entertainment/movies/jailer-2-review",
    ) == "entertainment"


def test_non_reporting_pages_stay_out_without_excluding_dated_news_about_tools():
    row = report()
    row["url"] = "https://news.example/business/tools-and-calculators/car-loan-emi-calculator"
    assert not is_reporting_page(row)
    row["url"] = "https://news.example/technology/tech-tips-and-tricks"
    row["title"] = "Tech Tips and Tricks in Hindi: Latest Technology Hacks"
    row["date_basis"] = "first_captured"
    assert not is_reporting_page(row)
    assert not group_reports([row], DigestFilters())
    row.update(date_basis="published", title="Government launches a tax calculator for citizens")
    row["url"] = "https://news.example/news/government-launches-tax-calculator"
    assert is_reporting_page(row)


def test_filters_normalize_and_reject_unbounded_or_unknown_input():
    filters = DigestFilters(keywords=[" Cricket ", "CRICKET"], languages=["EN", "en"])
    assert filters.keywords == ["cricket"]
    assert filters.languages == ["en"]
    for values in ({"topics": ["made_up"]}, {"keywords": ["x"] * 21},
                   {"languages": [""]}, {"admin": True}):
        with pytest.raises(ValidationError):
            DigestFilters(**values)
    with pytest.raises(ValidationError, match="timezone"):
        DigestRequest(as_of=datetime(2026, 10, 23))
    with pytest.raises(ValidationError):
        StreamInput(name="   ")


def test_duplicate_coverage_keeps_both_publishers_and_excerpt_attribution():
    first, second = report(), report()
    second["published_at"] = NOW + timedelta(minutes=2)
    second["publisher_name"] = "Second news"
    stories = group_reports([first, second], DigestFilters())
    assert len(stories) == 1
    assert stories[0].report_count == 2
    assert len(stories[0].sources) == 2
    assert stories[0].sources[0].publisher_name == "Second news"
    # Matching one report must not bring an excluded report into its source list.
    first["text"] += " Bengaluru"
    filtered = group_reports([first, second], DigestFilters(keywords=["bengaluru"]))
    assert filtered[0].report_count == 1
    assert filtered[0].sources[0].publisher_name == "Example news"


def test_different_updates_are_not_collapsed_only_because_event_matches():
    first, second = report(), report()
    second.update(event_id=first["event_id"], title="Markets respond to the policy decision")
    assert len(group_reports([first, second], DigestFilters())) == 2
    first["text"] += " Further details followed in a statement."
    second["text"] = first["text"]
    second["content_hash"] = first["content_hash"]
    assert len(group_reports([first, second], DigestFilters())) == 1


def test_two_minute_selection_respects_budget_and_diversity():
    rows = []
    one_publisher = uuid4()
    for i in range(80):
        row = report()
        row.update(title=f"Central bank announces policy decision number {i}",
                   publisher_id=one_publisher, published_at=NOW - timedelta(minutes=i))
        rows.append(row)
    sports = report()
    sports.update(title="Cricket team wins the championship final",
                  text="The cricket team won the championship final after a close match on Friday.",
                  published_at=NOW - timedelta(hours=2))
    rows.append(sports)
    stories = group_reports(rows, DigestFilters())
    selected = short_edition(stories)
    assert 1 < len(selected) <= 12
    assert sum(item_words(item) for item in selected) <= WORD_BUDGET
    assert len(selected) < len(stories)
    assert "sports" in {item.topic for item in selected}
    assert len({item.sources[0].publisher_id for item in selected}) > 1


def test_topic_and_exclusion_filters_do_not_leak_reports():
    row = report()
    assert not group_reports([row], DigestFilters(topics=["sports"]))
    assert not group_reports([row], DigestFilters(exclude_keywords=["interest rate"]))
    row["url"] = "javascript:alert(1)"
    assert group_reports([row], DigestFilters())[0].sources[0].url is None


def test_viewer_can_save_stream_and_only_authenticated_owner_id_is_passed():
    app = create_app()
    user_id = uuid4()
    user = SimpleNamespace(id=user_id, role=AccessRole.VIEWER,
                           access_status=AccessStatus.APPROVED, access_expires_at=None,
                           permissions={p.value for p in permissions_for_role(AccessRole.VIEWER)})
    service = AsyncMock()
    saved = SavedStream(id=uuid4(), name="My cricket", period="weekly",
                        filters=DigestFilters(keywords=["cricket"]), created_at=NOW, updated_at=NOW)
    service.save_stream.return_value = saved
    service.streams.return_value = [saved]
    service.preferences.return_value = ReadingPreferences()
    service.save_preferences.return_value = ReadingPreferences(period="weekly")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_digest_service] = lambda: service
    with TestClient(app) as client:
        response = client.post("/api/v1/digest-streams", json={
            "name": "My cricket", "period": "weekly", "filters": {"keywords": ["Cricket"]},
        })
        assert response.status_code == 201
        assert response.json()["filters"]["keywords"] == ["cricket"]
        assert service.save_stream.await_args.args[0] == user_id
        assert client.get("/api/v1/digest-streams").status_code == 200
        assert client.get("/api/v1/digests/preferences").status_code == 200
        assert service.preferences.await_args.args[0] == user_id
        assert client.put("/api/v1/digests/preferences", json={"period":"weekly"}).status_code == 200
        assert service.save_preferences.await_args.args[0] == user_id
        assert client.put("/api/v1/digests/preferences", json={"user_id":str(uuid4())}).status_code == 422
        page = client.get("/briefs")
        assert page.status_code == 200
        assert page.headers["cache-control"] == "private, no-store"
        assert "Catch up in two minutes." in page.text
        user.access_status = AccessStatus.SUSPENDED
        assert client.get("/briefs").status_code == 403
        assert client.post("/api/v1/digests/preview", json={}).status_code == 403
        assert client.delete(f"/api/v1/digest-streams/{saved.id}").status_code == 403


def test_stream_and_edition_input_errors_are_reviewable_http_errors():
    app = create_app()
    user = SimpleNamespace(id=uuid4(), access_status=AccessStatus.APPROVED,
                           access_expires_at=None,
                           permissions={p.value for p in permissions_for_role(AccessRole.VIEWER)})
    service = AsyncMock()
    service.edition.side_effect = ValueError("The edition time cannot be in the future")
    service.delete_stream.side_effect = LookupError("Stream not found")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_digest_service] = lambda: service
    with TestClient(app) as client:
        assert client.post("/api/v1/digests/preview", json={}).status_code == 422
        assert client.post("/api/v1/digests/preview", json={"period": "monthly"}).status_code == 422
        assert client.delete(f"/api/v1/digest-streams/{uuid4()}").status_code == 404


def test_excerpt_ignores_navigation_and_repeated_title_but_keeps_attributed_fact():
    headline = "Flood warning issued for five coastal districts"
    fact = "Officials said 12 shelters would open overnight while the cyclone warning remains in force."
    text = ("Written by the news desk and updated: October 23, 2026.\n"
            + headline + ".\n" + fact + " Subscribe to our newsletter for more updates.")
    assert source_line(text, headline) == fact


def test_cleaner_report_supplies_excerpt_and_primary_source_in_group():
    first, thin = report(), report()
    thin.update(text="Subscribe to read the full story and support our journalism.",
                published_at=NOW+timedelta(minutes=10), publisher_name="Thin copy")
    stories = group_reports([thin, first], DigestFilters())
    assert len(stories) == 1
    assert stories[0].summary_available
    assert stories[0].article_id == first["article_id"]
    assert stories[0].sources[0].article_id == first["article_id"]
    assert len(stories[0].sources) == 2


def test_near_matching_coverage_groups_but_different_numbers_and_denials_stay_separate():
    first, second = report(), report()
    first.update(title="Central bank cuts interest rates by 25 basis points after inflation eases")
    second.update(title="Central bank cuts interest rates by 25 basis points as inflation eases")
    assert len(group_reports([first, second], DigestFilters())) == 1
    second["title"] = second["title"].replace("25", "50")
    assert len(group_reports([first, second], DigestFilters())) == 2
    second["title"] = first["title"].replace("cuts", "denies cuts")
    assert len(group_reports([first, second], DigestFilters())) == 2


def test_short_brief_omits_service_and_unusable_capture_but_custom_stream_retains_service():
    service, weak, ordinary = report(), report(), report()
    service.update(title="Daily horoscope and astrology forecast for every star sign",
                   url="https://news.example/astrology/horoscope", event_id=None,
                   text="The horoscope forecast describes how each star sign may approach the coming week.")
    weak.update(title="Government confirms the national election timetable",
                text="Subscribe to read the full article and the latest updates.")
    stories = group_reports([service, weak, ordinary], DigestFilters())
    assert len(stories) == 3
    selected = short_edition(stories)
    assert [item.article_id for item in selected] == [ordinary["article_id"]]
    custom_filters = DigestFilters(topics=["lifestyle"])
    personalized = group_reports([service, weak, ordinary], custom_filters)
    assert short_edition(personalized, filters=custom_filters)[0].report_type == "service"


def test_weekly_leads_with_major_earlier_development_instead_of_latest_routine_update():
    older, recent = report(), report()
    older.update(title="Supreme court delivers election verdict after parliament vote",
                 text="The judges said the decision requires a fresh national vote within three months.",
                 published_at=NOW-timedelta(days=5))
    recent.update(title="Local council discusses plans during its regular morning meeting",
                  text="The council said discussions would continue at the next scheduled meeting on Monday.")
    stories = group_reports([older, recent], DigestFilters())
    daily = short_edition(stories, as_of=NOW)
    weekly = short_edition(stories, period="weekly", as_of=NOW)
    assert daily[0].article_id == recent["article_id"]
    assert weekly[0].article_id == older["article_id"]
    assert len({item.published_at.date() for item in weekly}) == 2


def test_known_poor_extraction_is_not_promoted_and_opinion_is_labelled():
    weak, opinion = report(), report()
    weak.update(extraction_quality=.1)
    opinion.update(title="A columnist assesses the new national policy",
                   url="https://news.example/opinion/policy",
                   text="The columnist argues the national policy needs stronger safeguards before implementation.")
    stories = group_reports([weak, opinion], DigestFilters())
    assert not next(item for item in stories if item.article_id == weak["article_id"]).summary_available
    assert not short_edition(stories)
    custom = DigestFilters(topics=["politics_government"])
    assert [item.report_type for item in short_edition(stories, filters=custom)] == ["opinion"]


def test_latest_update_gets_one_brief_slot_while_distinct_reported_numbers_remain_in_stream():
    first, update = report(), report()
    first.update(title="Earthquake kills at least 12 people in northern mountain region",
                 text="The emergency service said at least 12 people had died after the overnight earthquake.",
                 published_at=NOW-timedelta(hours=2))
    update.update(title="Earthquake kills at least 16 people in northern mountain region",
                  text="The emergency service said at least 16 people had died after the overnight earthquake.",
                  event_id=first["event_id"])
    stories = group_reports([first, update], DigestFilters())
    assert len(stories) == 2
    selected = short_edition(stories, as_of=NOW)
    assert [item.article_id for item in selected] == [update["article_id"]]
    assert "at least 16" in selected[0].explanation


def test_excerpt_keeps_early_uncertainty_instead_of_promoting_unqualified_number():
    qualification = "Police said initial reports of arrests after the protest have not been confirmed."
    text = qualification + " Local accounts describe 20 people being taken away in vehicles."
    assert source_line(text, "Police investigate reports of arrests after protest") == qualification


def test_summary_skips_publisher_related_story_lists_and_image_metadata():
    title = "WHO warns Ebola outbreak is spreading across three countries"
    lead = "The World Health Organization says cases are now present in countries in East and West Africa."
    text = (lead + "\nlist 2 of 3 Kenya confirms four more Ebola cases, bringing total to seven\n"
            "Getty Images/iStockphoto https://images.example/photo.jpg Photo credit: News desk")
    assert source_line(text, title) == lead
    title = "USA to host women's football Club World Cup in 2028 - FIFA"
    text = (title + " left FIFA is the international governing body of association football. "
            "Getty Images https://images.example/fifa.jpg Photo credit: News desk. "
            "The first women's Club World Cup will be staged from January 5-30, 2028.")
    assert source_line(text, title) == (
        "The first women's Club World Cup will be staged from January 5-30, 2028."
    )


def test_rhetorical_questions_and_letters_do_not_replace_news_facts():
    from newsintel.domain.intelligence.digest_quality import report_type

    title = "India addresses Pakistan over Kargil war at United Nations"
    fact = "India said Pakistan had refused to accept the bodies of soldiers killed during the Kargil war."
    assert source_line("What benefit does the report derive by mentioning similar tragic situations?\n"
                       + fact, title) == fact
    assert report_type("Letters to The Editor — October 23, 2026",
                       "https://news.example/news/letters-to-editor") == "opinion"


def test_summary_prefers_decision_details_over_generic_reactions_and_splits_joined_sentences():
    title = "सुप्रीम कोर्ट से ट्रंप प्रशासन को झटका, कैदियों के हेल्थकेयर बैन पर रोक"
    detail = "सुप्रीम कोर्ट ने ट्रांसजेंडर कैदियों के इलाज पर पाबंदी को रोकने का आदेश बरकरार रखा है."
    assert source_line("अमेरिका के सुप्रीम कोर्ट ने ट्रंप प्रशासन को बड़ा झटका दिया.\n"
                       + detail, title) == detail
    detail = "The minister said police will investigate the killing of two campaigners in Punjab."
    assert source_line('May God grant them the strength to bear this sorrow," the minister said.\n'
                       + detail, "Minister meets families of campaigners killed in Punjab") == detail
    first = "Police confirmed 20 protesters were arrested after the rally."
    assert source_line(first + "Officials said the investigation is continuing.",
                       "Police confirm arrests after protest rally") == first


def test_identical_headlines_do_not_hide_differing_counts_or_denials():
    first, update = report(), report()
    first.update(title="Earthquake rescue efforts continue in coastal region",
                 text="Officials said at least 12 people have been killed in the earthquake and 100 remain missing.")
    update.update(title=first["title"],
                  text="Officials said at least 40 people have been killed in the earthquake and 200 remain missing.")
    assert len(group_reports([first, update], DigestFilters())) == 2
    first.update(title="Police investigate reports of arrests after protest",
                 text="Police said reports of arrests after the protest have been confirmed by investigators.")
    update.update(title=first["title"],
                  text="Police said reports of arrests after the protest have not been confirmed by investigators.")
    assert len(group_reports([first, update], DigestFilters())) == 2


def test_opinion_cannot_absorb_matching_news_and_remove_it_from_short_brief():
    news, opinion = report(), report()
    opinion.update(title=news["title"], text=news["text"], content_hash=news["content_hash"],
                   url="https://news.example/opinion/policy", published_at=NOW+timedelta(minutes=1))
    stories = group_reports([opinion, news], DigestFilters())
    assert len(stories) == 2
    assert [item.article_id for item in short_edition(stories)] == [news["article_id"]]


def test_excerpt_does_not_cut_off_late_negation_or_attribution():
    title = "Health ministry reviews proposed nationwide vaccination campaign"
    premise = ("The health ministry said the proposed nationwide vaccination campaign, which would involve "
               "all public hospitals, regional clinics, schools, universities and care homes across the "
               "country during the coming winter, ")
    for ending in ("has not been approved.", "was announced, according to an unconfirmed social media post."):
        assert source_line(premise+ending, title) == (
            "Source text unavailable. Open the original report for details."
        )
    complete = "The ministry said the vaccination campaign is still under review."
    assert source_line(premise+"has not been approved.\n"+complete, title) == complete


def test_long_headline_preserves_final_qualification_and_counts_toward_reading_budget():
    row = report()
    row["title"] = ("The proposed nationwide vaccination campaign covering public hospitals, regional "
                    "clinics, schools, universities and care homes across the country during the "
                    "coming winter has not been approved")
    row["text"] = "The ministry said the vaccination campaign remains under review by medical experts."
    item, = group_reports([row], DigestFilters())
    assert item.title == row["title"]
    selected = short_edition([item], as_of=NOW)
    assert selected and selected[0].title.endswith("has not been approved")
    assert sum(item_words(entry) for entry in selected) <= 360


def test_school_actors_do_not_override_clear_health_or_national_election_subjects():
    assert news_topic("Thousands gather at final student-led rally ahead of Serbia election") == (
        "politics_government"
    )
    assert news_topic("University researchers discover vaccine to prevent cancer") == "science_health"
    assert news_topic("University students will take the final exam") == "education"
    assert news_topic("Students elect university president") == "education"


def test_archive_reprints_are_labelled_and_do_not_become_current_default_news():
    archive, current = report(), report()
    archive.update(
        title="From The Hindu Archives, October 27, 1976: Foreign bank accounts: 400 cases detected",
        url="https://www.thehindu.com/archives/from-the-hindu-archives-october-27-1976/article.ece",
        text="Foreign bank accounts were investigated in 1976, with 400 cases detected by the authorities.",
    )
    stories = group_reports([archive, current], DigestFilters())
    assert len(stories) == 2
    assert next(item for item in stories if item.article_id == archive["article_id"]).report_type == "archive"
    assert [item.article_id for item in short_edition(stories)] == [current["article_id"]]
    filters = DigestFilters(keywords=["1976"])
    # Personalization must not relabel archive material as current news.
    matches = group_reports([archive, current], filters)
    assert matches[0].freshness_status == "historical"
    assert short_edition(matches, filters=filters) == []


@pytest.mark.parametrize("changes,status", [
    ({"date_basis": "first_captured"}, "date_unconfirmed"),
    ({"title": "Live updates October 20, 2026: Flood response expands"}, "expired"),
    ({"title": "आज का राशिफल 20 अक्टूबर 2026: दैनिक भविष्यफल"}, "expired"),
    ({"title": "From the archives: Central bank announces policy"}, "historical"),
    ({"title": "Flood response expands after lessons from 1976"}, "current"),
])
def test_freshness_gates_are_preserved_under_personalization(changes, status):
    row = report()
    row["text"] = "Officials said the flood response would open ten emergency shelters in affected districts."
    row.update(changes)
    stories = group_reports([row], DigestFilters(), as_of=NOW)
    assert stories[0].freshness_status == status
    selected = short_edition(stories, as_of=NOW, filters=DigestFilters(keywords=["flood"]))
    assert bool(selected) == (status == "current")


def test_weekly_live_session_expiry_uses_snapshot_instead_of_wall_clock():
    row = report()
    row.update(title="Cyclone live updates: Authorities open emergency shelters",
               published_at=NOW - timedelta(days=2))
    assert group_reports([row], DigestFilters(), as_of=NOW)[0].freshness_status == "expired"
    assert group_reports([row], DigestFilters(), as_of=row["published_at"])[0].freshness_status == "current"


def test_current_source_is_preferred_to_undated_duplicate():
    dated, undated = report(), report()
    undated.update(title=dated["title"], text=dated["text"], date_basis="first_captured",
                   published_at=NOW + timedelta(minutes=1))
    stories = group_reports([undated, dated], DigestFilters(), as_of=NOW + timedelta(minutes=2))
    assert len(stories) == 1
    assert stories[0].article_id == dated["article_id"]
    assert stories[0].freshness_status == "current"
    assert len(stories[0].sources) == 2


def test_similarity_grouping_cannot_overwrite_the_freshness_snapshot():
    first, similar, live = report(), report(), report()
    similar["title"] = first["title"] + " today"
    live["title"] = "Cyclone live updates October 20, 2026: Shelters open"
    stories = group_reports([first, similar, live], DigestFilters(), as_of=NOW)
    assert next(item for item in stories if item.article_id == live["article_id"]).freshness_status == "expired"


def test_short_excerpt_does_not_switch_to_a_different_named_person():
    title = "Sir Patrick Stewart was last seen watching his beloved football club before a tribute"
    unrelated = "Vaughan had worked with both Huddersfield and Bradford during his coaching career, making the occasion a joint tribute from the two clubs."
    relevant = "Patrick Stewart watched Huddersfield from the stands during the club's final home match."
    assert source_line(unrelated + "\n" + relevant, title) == relevant
    assert source_line(unrelated, title).startswith("Source text unavailable")
    assert source_line(
        "Ravichandran as DG, Export Promotion, New Delhi; Atul Kumar Rastogi as Chief Commissioner, CESTAT, New Delhi; and Satyajit Singh as Chief Commissioner, Panchkula.",
        "N. Sridhar is new Chief Commissioner GST, Visakhapatnam",
    ).startswith("Source text unavailable")
    assert source_line("India also advanced to the semifinals.",
                       "India extends winning run, seals spot in the semifinals").startswith("Source text unavailable")


def test_dated_school_roundups_expire_and_utility_advice_stays_out_of_default_brief():
    roundup, advice = report(), report()
    roundup.update(title="Today News Headlines for School Assembly, October 20, 2026: Flood warnings",
                   text="Schools received district flood warnings and emergency closure notices on Tuesday.")
    advice.update(title="Post office savings: How much a monthly deposit can earn",
                  url="https://news.example/business/utility/post-office-savings-guide",
                  text="The post office deposit scheme credits interest every quarter according to the published schedule.")
    stories = group_reports([roundup, advice], DigestFilters(), as_of=NOW)
    assert all(item.report_type == "service" for item in stories)
    assert next(item for item in stories if item.article_id == roundup["article_id"]).freshness_status == "expired"
    assert short_edition(stories, period="weekly", as_of=NOW) == []


def test_hindi_navigation_prefix_is_removed_without_losing_the_reporting_sentence():
    sentence = "पंजाब विधानसभा चुनाव 2027 के लिहाज से जिले की 3 विधानसभा सीटें राजनीतिक दलों के लिए अहम हैं."
    assert source_line("और पढ़ें"+sentence, "पंजाब विधानसभा चुनाव: बरनाला की 3 विधानसभा सीटें") == sentence
