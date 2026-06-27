from fable_meat_proxy.meat import build_message


def test_build_message_constructs_valid_anthropic_message():
    msg = build_message("claude-fable-5", "hello from meat", "abcd1234")
    assert msg.id == "msg_meat_abcd1234"
    assert msg.role == "assistant"
    assert msg.type == "message"
    assert msg.model == "claude-fable-5"
    assert msg.stop_reason == "end_turn"
    assert msg.content[0].type == "text"
    assert msg.content[0].text == "hello from meat"
    assert msg.usage.input_tokens == 0
    assert msg.usage.output_tokens == 0
