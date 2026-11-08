"""Provider-independent regressions for output budgets and unsafe responses."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from mem0.configs.llms.base import BaseLlmConfig
from mem0.configs.llms.openai import OpenAIConfig
from mem0.exceptions import LLMResponseError
from mem0.llms.base import LLMBase
from mem0.llms.openai import OpenAILLM


class StubLLM(LLMBase):
    def generate_response(self, messages, **kwargs):
        raise NotImplementedError


@pytest.mark.parametrize("model", ["gpt-4.1", "gpt-5.4-mini", "o3", "gpt-5"])
def test_default_omits_token_budget(model):
    params = StubLLM(BaseLlmConfig(model=model))._get_supported_params()
    assert "max_tokens" not in params
    assert "max_completion_tokens" not in params


@pytest.mark.parametrize(
    "model,key", [("gpt-4.1", "max_tokens"), ("gpt-5.4-mini", "max_completion_tokens"), ("o3", "max_completion_tokens")]
)
def test_explicit_budget_is_forwarded(model, key):
    assert StubLLM(BaseLlmConfig(model=model, max_tokens=123))._get_supported_params()[key] == 123


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2000"])
def test_invalid_budget_rejected(value):
    with pytest.raises(ValueError, match="max_tokens"):
        BaseLlmConfig(max_tokens=value)


@pytest.mark.parametrize(
    "content,reason,code",
    [
        ("partial", "length", "llm_response_truncated"),
        (None, "stop", "llm_empty_response"),
        ("   ", "stop", "llm_empty_response"),
    ],
)
def test_openai_rejects_invalid_responses(content, reason, code):
    with patch("mem0.llms.openai.OpenAI") as client:
        client.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason=reason, message=SimpleNamespace(content=content, tool_calls=None))]
        )
        llm = OpenAILLM(OpenAIConfig(model="gpt-4.1"))
        with pytest.raises(LLMResponseError) as exc:
            llm.generate_response([{"role": "user", "content": "test"}])
        assert exc.value.error_code == code


def test_tool_only_response_is_valid():
    llm = StubLLM(BaseLlmConfig(model="gpt-4.1"))
    llm._validate_chat_response(
        SimpleNamespace(
            choices=[
                SimpleNamespace(finish_reason="tool_calls", message=SimpleNamespace(content=None, tool_calls=[Mock()]))
            ]
        ),
        tools=[{}],
    )


@pytest.mark.parametrize("arguments", ['{"broken":', "[]", "null", '"secret response"'])
def test_invalid_tool_arguments_are_safe(arguments):
    with pytest.raises(LLMResponseError) as exc:
        StubLLM._parse_tool_arguments(arguments)
    assert exc.value.error_code == "llm_invalid_response"
    assert arguments not in str(exc.value)


def test_stream_rejected_before_provider_call():
    with patch("mem0.llms.openai.OpenAI") as client:
        llm = OpenAILLM(OpenAIConfig(model="o3"))
        with pytest.raises(ValueError, match="Streaming"):
            llm.generate_response([], stream=True)
        client.return_value.chat.completions.create.assert_not_called()


def test_numeric_finish_reason_enum_detects_truncation():
    from enum import IntEnum

    class FinishReason(IntEnum):
        STOP = 1
        MAX_TOKENS = 2

    with pytest.raises(LLMResponseError) as exc:
        StubLLM._check_finish_reason(FinishReason.MAX_TOKENS)
    assert exc.value.error_code == "llm_response_truncated"
    StubLLM._check_finish_reason(FinishReason.STOP)
