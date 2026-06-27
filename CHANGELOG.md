# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed (code-review hardening)
- `with_options(...)` now returns a proxy, so Fable routing survives chaining;
  `with_raw_response` / `with_streaming_response` reject Fable instead of silently
  hitting the real API.
- Reply matching uses exact parsed addresses and returns the latest reply
  (no substring/display-name false positives, no stale earliest reply).
- Request parameters (`temperature`, `tools`, `stop_sequences`, …) are surfaced in
  the email instead of being silently dropped.
- Async Gmail access is serialized with a lock (the googleapiclient service is not
  thread-safe under concurrent requests).
- Poll sleep is bounded by the remaining time so the deadline isn't overshot.
- base64url reply bodies are padded before decoding; quote-stripping preserves
  Markdown blockquotes and no longer treats `From:` lines as quote boundaries.
- Least-privilege Gmail scopes (`gmail.send` + `gmail.readonly`); `token.json`
  written `0600`; bogus `From: me` header omitted.

## [0.1.0] - 2026-06-28

### Added
- Drop-in `Anthropic` and `AsyncAnthropic` clients. Non-Fable models pass
  through to the real SDK; `model="claude-fable-5"` routes to a human over email.
- Gmail API transport (OAuth `gmail.modify`, send, thread polling) with
  transient-error retries (HTTP 429/5xx + network) and exponential backoff.
- Business-day reply timeout (default 7 business days, weekends skipped), with a
  raw-seconds override.
- Reply parsing: `text/plain` with an HTML fallback, plus quoted-text stripping.
- Custom errors: `FableMeatError`, `FableReplyTimeout`, `FableConfigError`.
- `fable-meat-auth` console script for the one-time Gmail OAuth flow.
- Typed package (`py.typed`), CI (Python 3.11–3.13), and Trusted-Publishing release workflow.

[Unreleased]: https://github.com/plwp/fable-meat-proxy/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/plwp/fable-meat-proxy/releases/tag/v0.1.0
