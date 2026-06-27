from fable_meat_proxy.parsing import (
    first_user_snippet,
    format_prompt_email,
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


def test_first_user_snippet_picks_first_user_turn():
    snippet = first_user_snippet(
        [
            {"role": "assistant", "content": "ignored"},
            {"role": "user", "content": "the real prompt"},
        ]
    )
    assert snippet == "the real prompt"


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
