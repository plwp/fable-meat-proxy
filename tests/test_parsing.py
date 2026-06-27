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


def test_html_to_text_strips_tags_and_scripts():
    html = "<style>x{}</style><p>Para one</p><p>Para &amp; two<br>line</p>"
    assert html_to_text(html) == "Para one\nPara & two\nline"
