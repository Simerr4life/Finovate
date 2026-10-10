"""Channel interface: anything that can deliver a reply to a user.

handle_incoming_message() in services.py never talks to a channel
directly — a channel only wraps *delivery* of the string it already
computed. That keeps the intent logic testable without any transport at
all (see LocalEchoChannel, used by chat_demo and the test suite) and
keeps a future real channel to a thin adapter.
"""

from abc import ABC, abstractmethod


class MessageChannel(ABC):
    @abstractmethod
    def send(self, user, text: str) -> None:
        """Deliver `text` to `user` on this channel."""


class LocalEchoChannel(MessageChannel):
    """No-op delivery — the caller already has the reply string and
    prints/returns it directly. Used by chat_demo and tests."""

    def send(self, user, text: str) -> None:
        pass
