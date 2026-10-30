from newsintel.adapters.artifacts.s3_store import _is_missing_object_error


class _FakeClientError(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


def test_missing_object_errors_are_recognized() -> None:
    assert _is_missing_object_error(_FakeClientError("404"))
    assert _is_missing_object_error(_FakeClientError("NoSuchKey"))
    assert _is_missing_object_error(_FakeClientError("NotFound"))


def test_permission_and_service_errors_are_not_treated_as_missing() -> None:
    assert not _is_missing_object_error(_FakeClientError("AccessDenied"))
    assert not _is_missing_object_error(RuntimeError("network unavailable"))
