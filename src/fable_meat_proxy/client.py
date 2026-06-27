"""Drop-in Anthropic client that routes Fable to the meat proxy."""

from __future__ import annotations

from .config import Config, is_fable_model
from .meat import complete_via_meat


class _Messages:
    """Stand-in for ``client.messages`` that intercepts ``create``."""

    def __init__(self, proxy: "Anthropic"):
        self._proxy = proxy

    def create(self, **kwargs):
        if is_fable_model(kwargs.get("model")):
            return self._proxy._complete_via_meat(**kwargs)
        return self._proxy._real.messages.create(**kwargs)


class Anthropic:
    """Passthrough Anthropic client.

    Every non-Fable model is delegated, unchanged, to the real ``anthropic.Anthropic``
    client. ``model="claude-fable-5"`` (anything containing "fable") is instead routed
    to a human over email and blocks until they reply.
    """

    def __init__(
        self,
        *args,
        config: Config | None = None,
        gmail_service=None,
        real_client=None,
        **kwargs,
    ):
        if real_client is not None:
            self._real = real_client
        else:
            from anthropic import Anthropic as _RealAnthropic

            self._real = _RealAnthropic(*args, **kwargs)
        self._config = config
        self._gmail_service = gmail_service
        self.messages = _Messages(self)

    def _complete_via_meat(self, **kwargs):
        config = self._config or Config.from_env()
        service = self._gmail_service
        if service is None:
            from .gmail_transport import build_service

            service = build_service(config)
            self._gmail_service = service  # cache for subsequent calls
        return complete_via_meat(config, service, **kwargs)

    def __getattr__(self, name):
        # Anything we don't override (e.g. .models, .beta, .with_options) falls
        # through to the real client. Guard against recursion before _real is set.
        if name == "_real":
            raise AttributeError(name)
        return getattr(self._real, name)
