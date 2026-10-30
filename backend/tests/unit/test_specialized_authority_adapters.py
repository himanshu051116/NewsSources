import json

from newsintel.adapters.evidence.specialized import (
    ckan_candidate_urls,
    configured_json_candidate_urls,
    socrata_candidate_urls,
)


def test_ckan_extracts_dataset_and_resource_urls() -> None:
    body = json.dumps({
        "success": True,
        "result": {
            "results": [{
                "name": "inflation-data",
                "resources": [{"url": "https://data.gov.example/files/inflation.csv"}],
            }]
        },
    }).encode()
    urls = ckan_candidate_urls(body, base_url="https://data.gov.example", max_results=5)
    assert "https://data.gov.example/dataset/inflation-data" in urls
    assert "https://data.gov.example/files/inflation.csv" in urls


def test_socrata_extracts_resource_api_url() -> None:
    body = json.dumps({
        "results": [{"resource": {"domain": "data.example.gov", "id": "abcd-1234"}}]
    }).encode()
    urls = socrata_candidate_urls(body, max_results=5)
    assert urls == ["https://data.example.gov/resource/abcd-1234.json"]


def test_configured_json_only_reads_approved_field_names() -> None:
    body = json.dumps({
        "items": [{
            "document_url": "/records/1",
            "tracking_url": "https://tracker.example/1",
        }]
    }).encode()
    urls = configured_json_candidate_urls(
        body,
        base_url="https://records.example.gov/search",
        candidate_fields=("document_url",),
        max_results=5,
    )
    assert urls == ["https://records.example.gov/records/1"]
