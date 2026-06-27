# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
