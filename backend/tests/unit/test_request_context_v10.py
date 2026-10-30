from newsintel.core.request_context import resolve_request_id


def test_preserves_safe_request_id() -> None:
    assert resolve_request_id("req-123:abc") == "req-123:abc"


def test_rejects_unsafe_or_oversized_request_id() -> None:
    unsafe = resolve_request_id("bad request id\nheader")
    oversized = resolve_request_id("x" * 129)
    assert unsafe != "bad request id\nheader"
    assert oversized != "x" * 129
    assert len(unsafe) == 32
    assert len(oversized) == 32
