from newsintel.domain.intelligence.correction_detection import detect_correction_candidate
from newsintel.domain.intelligence.versioning import diff_article_versions


def test_detects_explicit_retraction_as_candidate_not_automatic_verdict_change():
    diff = diff_article_versions(
        old_title="Report",
        old_text="The project cost 10 million dollars.",
        new_title="Report",
        new_text="This article has been retracted. The project cost 10 million dollars.",
    )
    result = detect_correction_candidate(new_title="Report", new_text="This article has been retracted.", version_diff=diff)
    assert result is not None
    assert result.suggested_kind == "retraction"
    assert result.requires_human_confirmation is True


def test_silent_numeric_revision_is_only_an_update_candidate():
    diff = diff_article_versions(
        old_title="Report",
        old_text="Officials said 31 people were affected in the incident.",
        new_title="Report",
        new_text="Officials said 13 people were affected in the incident.",
    )
    result = detect_correction_candidate(new_title="Report", new_text="Officials said 13 people were affected.", version_diff=diff)
    assert result is not None
    assert result.suggested_kind == "update"
    assert result.confidence < 0.8
