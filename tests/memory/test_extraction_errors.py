"""Extraction failures must not masquerade as successful empty memories."""

import asyncio
from unittest.mock import MagicMock

import pytest

from mem0.exceptions import LLMError, LLMResponseError
from mem0.memory.main import AsyncMemory, Memory, _parse_extraction_response


@pytest.fixture(params=[Memory, AsyncMemory], ids=["sync", "async"])
def memory(request):
    instance = object.__new__(request.param)
    instance.db = MagicMock()
    instance.db.get_last_messages.return_value = []
    instance.embedding_model = MagicMock()
    instance.vector_store = MagicMock()
    instance.vector_store.search.return_value = []
    instance.llm = MagicMock()
    instance.custom_instructions = None
    return instance


def extract(memory):
    result = memory._add_to_vector_store([{"role": "user", "content": "hello"}], {}, {"user_id": "u"}, True)
    return asyncio.run(result) if isinstance(memory, AsyncMemory) else result


@pytest.mark.parametrize(
    "response",
    [
        None,
        "",
        "  ",
        "<think>private</think>",
        '{"memory": [',
        "{}",
        "[]",
        "null",
        '{"memory": null}',
        '{"memory": {}}',
        '{"memory": "bad"}',
        '{"memory": [null]}',
        '{"memory": [{}]}',
        '{"memory": [{"text": 12}]}',
        '{"memory": [{"text": "  "}]}',
        '{"memory": [{"text": "valid"}, {}]}',
        '{"memory": [], "unfinished":',
    ],
)
def test_invalid_extraction_raises_without_writes(memory, response, caplog):
    memory.llm.generate_response.return_value = response
    with pytest.raises(LLMError) as exc:
        extract(memory)
    assert exc.value.error_code in {"llm_empty_response", "llm_invalid_response"}
    memory.db.save_messages.assert_not_called()
    memory.vector_store.insert.assert_not_called()
    memory.embedding_model.embed_batch.assert_not_called()
    assert "private" not in str(exc.value) + caplog.text


@pytest.mark.parametrize("response", ['{"memory": []}', '```json\n{"memory": []}\n```'])
def test_explicit_empty_extraction_is_success(memory, response):
    memory.llm.generate_response.return_value = response
    assert extract(memory) == []
    memory.db.save_messages.assert_called_once()


def test_provider_error_is_safe(memory, caplog):
    memory.llm.generate_response.side_effect = RuntimeError("secret prompt / api-key")
    with pytest.raises(LLMError) as exc:
        extract(memory)
    assert "secret" not in str(exc.value) + caplog.text
    assert exc.value.__suppress_context__
    memory.db.save_messages.assert_not_called()


def test_valid_extraction_entry_is_preserved():
    response = '{"memory": [{"text": "A useful fact", "attributed_to": "user"}]}'
    assert _parse_extraction_response(response) == [{"text": "A useful fact", "attributed_to": "user"}]


def test_truncated_response_error_is_preserved(memory):
    error = LLMResponseError("The LLM response was truncated.", error_code="llm_response_truncated")
    memory.llm.generate_response.side_effect = error
    with pytest.raises(LLMResponseError) as exc:
        extract(memory)
    assert exc.value is error
    memory.db.save_messages.assert_not_called()


def test_invalid_response_reaches_public_add(memory):
    memory.config = MagicMock()
    memory.config.llm.config = {}
    memory.llm.generate_response.return_value = '{"memory": ['
    with pytest.raises(LLMResponseError):
        result = memory.add("hello", user_id="u")
        if isinstance(memory, AsyncMemory):
            asyncio.run(result)
    memory.db.save_messages.assert_not_called()


def test_invalid_json_error_does_not_expose_body(memory, caplog):
    memory.llm.generate_response.return_value = '{"memory": [SECRET_RESPONSE_BODY'
    with pytest.raises(LLMResponseError) as exc:
        extract(memory)
    assert "SECRET_RESPONSE_BODY" not in str(exc.value) + caplog.text
    assert exc.value.__suppress_context__


@pytest.mark.parametrize("response", [None, "", "  "])
def test_procedural_empty_response_is_reported(memory, response):
    memory.llm.generate_response.return_value = response
    with pytest.raises(LLMResponseError) as exc:
        result = memory._create_procedural_memory([{"role": "user", "content": "hello"}])
        if isinstance(memory, AsyncMemory):
            asyncio.run(result)
    assert exc.value.error_code == "llm_empty_response"
    memory.vector_store.insert.assert_not_called()


def test_procedural_provider_error_is_safe(memory, caplog):
    memory.llm.generate_response.side_effect = RuntimeError("SECRET_PROVIDER_PAYLOAD")
    with pytest.raises(LLMError) as exc:
        result = memory._create_procedural_memory([{"role": "user", "content": "hello"}])
        if isinstance(memory, AsyncMemory):
            asyncio.run(result)
    assert "SECRET_PROVIDER_PAYLOAD" not in str(exc.value) + caplog.text
    assert exc.value.__suppress_context__
    memory.vector_store.insert.assert_not_called()
