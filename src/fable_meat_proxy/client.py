"""Drop-in Anthropic clients that route Fable to the meat proxy."""

from __future__ import annotations

import asyncio

from .config import Config, is_fable_model
from .meat import complete_via_meat, complete_via_meat_async

_STREAM_MSG = (
    "Streaming is not supported for the Fable meat proxy — a human reply arrives "
    "all at once. Use messages.create() without stream=True for Fable models."
)


class _Messages:
    """Stand-in for ``client.messages`` that intercepts ``create``/``stream``."""

    def __init__(self, proxy: "Anthropic"):
        self._proxy = proxy

    def create(self, **kwargs):
        if is_fable_model(kwargs.get("model")):
            if kwargs.get("stream"):
                raise NotImplementedError(_STREAM_MSG)
            return self._proxy._complete_via_meat(**kwargs)
        return self._proxy._real.messages.create(**kwargs)

    def stream(self, **kwargs):
        if is_fable_model(kwargs.get("model")):
            raise NotImplementedError(_STREAM_MSG)
        return self._proxy._real.messages.stream(**kwargs)

    def __getattr__(self, name):
        # count_tokens, batches, with_raw_response, … fall through to the real
        # messages resource. (Fable routing only applies to create()/stream().)
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._proxy._real.messages, name)


class _AsyncMessages:
    def __init__(self, proxy: "AsyncAnthropic"):
        self._proxy = proxy

    async def create(self, **kwargs):
        if is_fable_model(kwargs.get("model")):
            if kwargs.get("stream"):
                raise NotImplementedError(_STREAM_MSG)
            return await self._proxy._complete_via_meat(**kwargs)
        return await self._proxy._real.messages.create(**kwargs)

    def stream(self, **kwargs):
        if is_fable_model(kwargs.get("model")):
            raise NotImplementedError(_STREAM_MSG)
        return self._proxy._real.messages.stream(**kwargs)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._proxy._real.messages, name)


class _BaseProxy:
    _real: object

    def __getattr__(self, name):
        # Anything we don't override (.models, .beta, .with_options, …) falls
        # through to the real client. Guard against recursion before _real is set.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._real, name)


class Anthropic(_BaseProxy):
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

    def _ensure_service(self, config: Config):
        if self._gmail_service is None:
            from .gmail_transport import build_service

            self._gmail_service = build_service(config)
        return self._gmail_service

    def _complete_via_meat(self, **kwargs):
        config = self._config or Config.from_env()
        return complete_via_meat(config, self._ensure_service(config), **kwargs)


class AsyncAnthropic(_BaseProxy):
    """Async passthrough client. Mirrors :class:`Anthropic` for ``anthropic.AsyncAnthropic``."""

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
            from anthropic import AsyncAnthropic as _RealAsyncAnthropic

            self._real = _RealAsyncAnthropic(*args, **kwargs)
        self._config = config
        self._gmail_service = gmail_service
        self.messages = _AsyncMessages(self)

    async def _complete_via_meat(self, **kwargs):
        config = self._config or Config.from_env()
        if self._gmail_service is None:
            from .gmail_transport import build_service

            self._gmail_service = await asyncio.to_thread(build_service, config)
        return await complete_via_meat_async(config, self._gmail_service, **kwargs)
