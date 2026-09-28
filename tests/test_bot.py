import asyncio
from types import SimpleNamespace

import pytest
from telegram.ext import ApplicationHandlerStop

from buho.bot import describe_throttled, only_my_chat

MY_CHAT = 123


def _guard(chat_id: int | None) -> None:
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id) if chat_id else None)
    context = SimpleNamespace(bot_data={"env": SimpleNamespace(chat_id=MY_CHAT)})
    asyncio.run(only_my_chat(update, context))


def test_my_chat_passes() -> None:
    _guard(MY_CHAT)


@pytest.mark.parametrize("chat_id", [999, None])
def test_other_chats_are_ignored(chat_id: int | None) -> None:
    with pytest.raises(ApplicationHandlerStop):
        _guard(chat_id)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0x0, "Voltaje OK"),
        (0x50000, "Hubo bajo voltaje"),
        (0x50005, "Bajo voltaje AHORA"),
        (0x4, "CPU limitado"),
    ],
)
def test_throttled_flags(value: int, expected: str) -> None:
    assert expected in describe_throttled(value)
