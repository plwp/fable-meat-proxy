"""`fable-meat-auth` — run the Gmail OAuth flow once to mint token.json."""

from __future__ import annotations

from .config import Config
from .gmail_transport import build_service


def main() -> int:
    config = Config.from_env()
    service = build_service(config)
    profile = service.users().getProfile(userId="me").execute()
    print(f"Authenticated as {profile.get('emailAddress')}.")
    print(f"Token saved to {config.token_path}. Fable prompts will go to {config.friend_email}.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
