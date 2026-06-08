import logging

import structlog

from ethos_core.settings import settings


def configure_logging() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(message)s",
    )

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )


logger = structlog.get_logger()
