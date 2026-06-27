from conftest import b64, make_message

from fable_meat_proxy.parsing import (
    extract_message_text,
    first_user_snippet,
    format_prompt_email,
    html_to_text,
    strip_quoted_reply,
)


def test_format_prompt_email_includes_system_and_turns():
    body = format_prompt_email(
        model="claude-fable-5",
        messages=[{"role": "user", "content": "What is 2+2?"}],
        system="Be terse.",
        max_tokens=256,
        corr_id="abc123",
    )
    assert "Correlation ID: abc123" in body
    assert "Be terse." in body
    assert "What is 2+2?" in body
    assert "Max tokens: 256" in body


def test_format_prompt_email_handles_block_content():
    body = format_prompt_email(
        model="claude-fable-5",
        messages=[{"role": "user", "content": [{"type": "text", "text": "hi there"}]}],
        corr_id="x",
    )
    assert "hi there" in body


def test_format_prompt_email_handles_list_system():
    body = format_prompt_email(
        model="claude-fable-5",
        messages=[],
        system=[{"type": "text", "text": "system rule"}],
        corr_id="x",
    )
    assert "system rule" in body


def test_first_user_snippet_picks_first_user_turn():
    snippet = first_user_snippet(
        [
            {"role": "assistant", "content": "ignored"},
            {"role": "user", "content": "the real prompt"},
        ]
    )
    assert snippet == "the real prompt"


def test_first_user_snippet_empty():
    assert first_user_snippet([]) == "(no prompt)"


def test_strip_quoted_reply_removes_quote_and_signature():
    raw = (
        "Here is Fable's answer.\n"
        "It spans two lines.\n"
        "\n"
        "On Mon, Jun 28, 2026 at 9:00 AM Me <me@example.com> wrote:\n"
        "> original prompt\n"
        "> more quoted text\n"
    )
    assert strip_quoted_reply(raw) == "Here is Fable's answer.\nIt spans two lines."


def test_strip_quoted_reply_handles_no_quote():
    assert strip_quoted_reply("just the answer") == "just the answer"


def test_strip_quoted_reply_preserves_markdown_blockquotes():
    raw = "> a Fable blockquote\nregular line\n\nOn Mon wrote:\n> the original\n"
    assert strip_quoted_reply(raw) == "> a Fable blockquote\nregular line"


def test_strip_quoted_reply_keeps_from_lines_in_body():
    # A bare "From:" line is real answer text, not a quote boundary.
    assert strip_quoted_reply("From: the desk of Fable\nanswer") == (
        "From: the desk of Fable\nanswer"
    )


def test_format_prompt_email_renders_request_parameters():
    body = format_prompt_email(
        model="claude-fable-5",
        messages=[],
        corr_id="x",
        extra_params={"temperature": 0.7, "stop_sequences": ["STOP"], "stream": True},
    )
    assert "temperature: 0.7" in body
    assert "stop_sequences: ['STOP']" in body
    assert "stream" not in body  # not a notable generation param


def test_extract_message_text_plain():
    assert extract_message_text(make_message("m1", "x@y", "hello world")) == "hello world"


def test_extract_message_text_prefers_plain_over_html():
    msg = {
        "payload": {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/html", "body": {"data": b64("<p>hi html</p>")}},
                {"mimeType": "text/plain", "body": {"data": b64("hi plain")}},
            ],
        }
    }
    assert extract_message_text(msg) == "hi plain"


def test_extract_message_text_html_fallback():
    msg = {
        "payload": {
            "mimeType": "text/html",
            "body": {"data": b64("<div>only<br>html</div>")},
        }
    }
    assert extract_message_text(msg) == "only\nhtml"


def test_extract_message_text_unpadded_base64():
    # Gmail can return base64url without "=" padding; decoding must still work.
    import base64 as _b64

    data = _b64.urlsafe_b64encode(b"hello!").decode().rstrip("=")
    msg = {"payload": {"mimeType": "text/plain", "body": {"data": data}}}
    assert extract_message_text(msg) == "hello!"


def test_html_to_text_strips_tags_and_scripts():
    html = "<style>x{}</style><p>Para one</p><p>Para &amp; two<br>line</p>"
    assert html_to_text(html) == "Para one\nPara & two\nline"
