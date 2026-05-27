"""Stats plugin command and handler registration."""
from __future__ import annotations

from telegram.ext import Application, BaseHandler

from yoink.core.plugin import HandlerSpec


def get_handler_specs() -> list[HandlerSpec]:
    from yoink_stats.commands.stats import register as reg_stats
    from yoink_stats.commands.import_cmd import register as reg_import
    from yoink_stats.collector.listener import register as reg_listener

    class _Shim(Application):  # type: ignore[type-arg,misc]
        """Quacks like Application.add_handler; only the one method matters."""
        def __init__(self) -> None:  # noqa: PLW0231
            self.specs: list[HandlerSpec] = []

        def add_handler(self, handler: BaseHandler, group: int = 0, **_: object) -> None:
            self.specs.append(HandlerSpec(handler=handler, group=group))

    shim = _Shim()
    reg_stats(shim)
    reg_import(shim)
    reg_listener(shim)
    return shim.specs
