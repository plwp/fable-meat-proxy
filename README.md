# fable-meat-proxy 🥩

A drop-in replacement for the Anthropic Python client where **Fable's inference is
performed by a human**.

Every real model passes straight through to the genuine `anthropic.Anthropic` client.
But when you select Fable (`model="claude-fable-5"` — anything containing `"fable"`),
the proxy instead **emails the prompt to your American friend**, blocks while polling
Gmail for their reply, and returns that reply as a normal Anthropic `Message`. A meat
proxy: the model is a person.

```mermaid
flowchart LR
    A[client.messages.create] --> B{model contains<br/>'fable'?}
    B -- no --> C[real anthropic.Anthropic] --> D[API response]
    B -- yes --> E[email prompt via Gmail API] --> F[friend pastes into Fable]
    F --> G[friend replies to email] --> H[poll thread, parse reply] --> I[Message]
```

## Install

```bash
pip install -e .          # runtime
pip install -e '.[dev]'   # + pytest
```

## Configure

Copy `.env.example` to `.env` and fill it in:

| Variable | Purpose |
| --- | --- |
| `FABLE_FRIEND_EMAIL` | **Required.** Where Fable prompts are sent. |
| `FABLE_GMAIL_CREDENTIALS` | OAuth client secret (Desktop app) from Google Cloud. |
| `FABLE_GMAIL_TOKEN` | Where the minted OAuth token is cached. |
| `FABLE_REPLY_TIMEOUT` | Seconds to block waiting for the reply (default `3600`). |
| `FABLE_POLL_INTERVAL` | Seconds between Gmail polls (default `15`). |
| `ANTHROPIC_API_KEY` | Standard key for the real (non-Fable) passthrough. |

### One-time Gmail auth

1. In Google Cloud Console, enable the **Gmail API** and create an **OAuth client ID**
   of type *Desktop app*. Download it as `credentials.json`.
2. Run the OAuth flow once to mint `token.json`:

   ```bash
   fable-meat-auth
   ```

The scope used is `gmail.modify` (send + read of your own account).

## Use

```python
from fable_meat_proxy import Anthropic

client = Anthropic()  # config + Gmail service resolved from the environment

# Real model: ordinary API call.
client.messages.create(
    model="claude-opus-4-8", max_tokens=1024,
    messages=[{"role": "user", "content": "hi"}],
)

# Fable: emails your friend, blocks until they reply, returns their answer.
msg = client.messages.create(
    model="claude-fable-5", max_tokens=1024,
    messages=[{"role": "user", "content": "Write a haiku about meat."}],
)
print(msg.content[0].text)  # whatever your friend pasted back
```

Your friend receives a formatted email (system prompt + conversation), pastes it into
Fable, and **replies with Fable's output as the plain-text body**. The text above the
quoted original is taken as the answer.

## How it works

- `client.py` — the wrapping `Anthropic`; routes on the model name, delegates everything
  else (`.models`, `.beta`, …) to the real client via `__getattr__`.
- `meat.py` — the human backend: format → send → block on reply → build a `Message`.
- `gmail_transport.py` — OAuth, send, and thread polling.
- `parsing.py` — render the outgoing email and strip quoted text from the reply.

## Test

```bash
pytest
```

Tests mock the Gmail service and the real Anthropic client, so they run offline and
cover routing, reply parsing, polling/timeout, and `Message` construction. The Gmail
OAuth round-trip itself needs your real credentials.

## Caveats

- **Latency is measured in human attention span.** Calls block until your friend replies.
- Streaming, tool use, and token accounting are not modeled for Fable (usage is reported
  as zero). Non-Fable models keep the full real SDK behaviour.
