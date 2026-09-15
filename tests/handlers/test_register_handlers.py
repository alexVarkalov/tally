from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from telegram.ext import CommandHandler

from tally.handlers import register_handlers
from tally.handlers.errors import on_error


def test_register_handlers_wires_every_handler_and_the_error_handler() -> None:
    app = SimpleNamespace(add_handler=Mock(), add_error_handler=Mock(), bot_data={})

    register_handlers(app)

    handlers = [call.args[0] for call in app.add_handler.call_args_list]
    commands = {name for h in handlers if isinstance(h, CommandHandler) for name in h.commands}
    assert commands == {"start", "help", "timezone", "tz", "users", "allow_user", "block_user"}
    assert len(handlers) == 7
    app.add_error_handler.assert_called_once_with(on_error)
