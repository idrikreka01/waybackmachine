import logging

from waybackmachine.logging_config import configure_logging


def test_configure_logging():
    configure_logging("DEBUG")
    log = logging.getLogger("waybackmachine")
    log.debug("test_message")
