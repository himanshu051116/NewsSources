import logging

from newsintel.core.logging import configure_logging


def test_configure_logging_suppresses_http_client_url_logging() -> None:
    configure_logging("INFO")

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
