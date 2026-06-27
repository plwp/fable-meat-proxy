"""fable-meat-proxy: a passthrough Anthropic client whose Fable backend is a human.

    from fable_meat_proxy import Anthropic

    client = Anthropic()  # reads config from the environment / .env

    # Real model -> normal API call.
    client.messages.create(model="claude-opus-4-8", max_tokens=1024, messages=[...])

    # Fable -> emails your friend and blocks (up to 7 business days) for their reply.
    client.messages.create(model="claude-fable-5", max_tokens=1024, messages=[...])
"""

from .client import Anthropic, AsyncAnthropic
from .config import Config, is_fable_model
from .errors import FableConfigError, FableMeatError, FableReplyTimeout

__all__ = [
    "Anthropic",
    "AsyncAnthropic",
    "Config",
    "is_fable_model",
    "FableMeatError",
    "FableReplyTimeout",
    "FableConfigError",
]
__version__ = "0.1.0"
