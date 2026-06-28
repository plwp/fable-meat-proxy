"""Drop-in Anthropic clients that route Fable to the meat proxy."""

from __future__ import annotations

import asyncio

from .config import Config, fable_models_from_env, is_fable_model
from .errors import FableMeatError
from .meat import complete_via_meat, complete_via_meat_async

_STREAM_MSG = (
    "Streaming is not supported for the Fable meat proxy — a human reply arrives "
    "all at once. Use messages.create() without stream=True for Fable models."
)
_RAW_MSG = (
    "Fable routing is not available via with_raw_response / with_streaming_response "
    "(they return wire-level responses a human reply can't satisfy). Use "
    "messages.create() for Fable models."
)
_COUNT_TOKENS_MSG = (
    "count_tokens is not available for Fable models — the backend is a human, so "
    "token accounting is undefined. Count against a real model instead."
)


class _RoutedResponseProxy:
    """Wraps messages.with_raw_response / with_streaming_response.

    Non-Fable calls delegate to the real wrapper; Fable calls raise rather than
    silently bypassing the meat proxy and hitting the real API.
    """

    def __init__(self, real_wrapper, fable_models):
        self._real = real_wrapper
        self._fable_models = fable_models

    def create(self, **kwargs):
        if is_fable_model(kwargs.get("model"), self._fable_models):
            raise NotImplementedError(_RAW_MSG)
        return self._real.create(**kwargs)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._real, name)


class _Messages:
    """Stand-in for ``client.messages`` that intercepts ``create``/``stream``."""

    def __init__(self, proxy: "Anthropic"):
        self._proxy = proxy

    def create(self, **kwargs):
        if is_fable_model(kwargs.get("model"), self._proxy._fable_models):
            if kwargs.get("stream"):
                raise NotImplementedError(_STREAM_MSG)
            return self._proxy._complete_via_meat(**kwargs)
        return self._proxy._real.messages.create(**kwargs)

    def stream(self, **kwargs):
        if is_fable_model(kwargs.get("model"), self._proxy._fable_models):
            raise NotImplementedError(_STREAM_MSG)
        return self._proxy._real.messages.stream(**kwargs)

    def count_tokens(self, **kwargs):
        # A human reply has no meaningful token count; reject rather than silently
        # forwarding a Fable model to the real token counter.
        if is_fable_model(kwargs.get("model"), self._proxy._fable_models):
            raise FableMeatError(_COUNT_TOKENS_MSG)
        return self._proxy._real.messages.count_tokens(**kwargs)

    @property
    def with_raw_response(self):
        return _RoutedResponseProxy(
            self._proxy._real.messages.with_raw_response, self._proxy._fable_models
        )

    @property
    def with_streaming_response(self):
        return _RoutedResponseProxy(
            self._proxy._real.messages.with_streaming_response, self._proxy._fable_models
        )

    def __getattr__(self, name):
        # batches, … fall through to the real messages resource. (Fable routing
        # applies to create()/stream()/count_tokens() and the response wrappers.)
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._proxy._real.messages, name)


class _AsyncMessages:
    def __init__(self, proxy: "AsyncAnthropic"):
        self._proxy = proxy

    async def create(self, **kwargs):
        if is_fable_model(kwargs.get("model"), self._proxy._fable_models):
            if kwargs.get("stream"):
                raise NotImplementedError(_STREAM_MSG)
            return await self._proxy._complete_via_meat(**kwargs)
        return await self._proxy._real.messages.create(**kwargs)

    def stream(self, **kwargs):
        if is_fable_model(kwargs.get("model"), self._proxy._fable_models):
            raise NotImplementedError(_STREAM_MSG)
        return self._proxy._real.messages.stream(**kwargs)

    async def count_tokens(self, **kwargs):
        if is_fable_model(kwargs.get("model"), self._proxy._fable_models):
            raise FableMeatError(_COUNT_TOKENS_MSG)
        return await self._proxy._real.messages.count_tokens(**kwargs)

    @property
    def with_raw_response(self):
        return _RoutedResponseProxy(
            self._proxy._real.messages.with_raw_response, self._proxy._fable_models
        )

    @property
    def with_streaming_response(self):
        return _RoutedResponseProxy(
            self._proxy._real.messages.with_streaming_response, self._proxy._fable_models
        )

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._proxy._real.messages, name)


class _BaseProxy:
    _real: object

    def __getattr__(self, name):
        # Anything we don't override (.models, .beta, …) falls through to the real
        # client. Guard against recursion before _real is set.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._real, name)

    def with_options(self, **kwargs):
        # The real with_options() returns a fresh real client; re-wrap it so Fable
        # routing survives chaining (client.with_options(...).messages.create(...)).
        return type(self)(
            real_client=self._real.with_options(**kwargs),
            config=self._config,
            gmail_service=self._gmail_service,
        )


class Anthropic(_BaseProxy):
    """Passthrough Anthropic client.

    Every non-Fable model is delegated, unchanged, to the real ``anthropic.Anthropic``
    client. A model in the Fable allowlist (``{"claude-fable-5"}`` by default; override
    via ``FABLE_MODELS`` or ``Config.fable_models``) is instead routed to a human over
    email and blocks until they reply. Matching is exact, never a substring.
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
        # Routing must be decided on every create() without building a full Config
        # (which needs friend_email). Resolve the allowlist eagerly from config or env.
        self._fable_models = config.fable_models if config is not None else fable_models_from_env()
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
        self._fable_models = config.fable_models if config is not None else fable_models_from_env()
        # Serializes access to the shared, not-thread-safe Gmail service across
        # concurrent Fable requests.
        self._gmail_lock = asyncio.Lock()
        self.messages = _AsyncMessages(self)

    async def _complete_via_meat(self, **kwargs):
        config = self._config or Config.from_env()
        if self._gmail_service is None:
            from .gmail_transport import build_service

            self._gmail_service = await asyncio.to_thread(build_service, config)
        return await complete_via_meat_async(
            config, self._gmail_service, lock=self._gmail_lock, **kwargs
        )
