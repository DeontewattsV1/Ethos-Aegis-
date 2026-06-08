from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from ethos_core.logging import logger


EventHandler = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[
            str,
            list[EventHandler]
        ] = defaultdict(list)

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        self._subscribers[event_type].append(handler)

    def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:

        logger.info(
            "event.published",
            event_type=event_type,
            payload=payload,
        )

        handlers = self._subscribers.get(
            event_type,
            []
        )

        for handler in handlers:
            handler(payload)
