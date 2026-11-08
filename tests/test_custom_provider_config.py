"""Offline regression tests; no provider calls, database, or real credentials."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[1] / "server"
spec = importlib.util.spec_from_file_location("provider_config", SERVER / "provider_config.py")
provider_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider_config)
prepare = provider_config.prepare_provider_updates


def config():
    return {
        "llm": {"provider": "openai", "config": {"api_key": "test-llm", "openai_base_url": "http://llm.test/v1"}},
        "embedder": {
            "provider": "openai",
            "config": {"api_key": "test-embed", "openai_base_url": "http://embed.test/v1"},
        },
    }


class ProviderTests(unittest.TestCase):
    def test_independent_endpoints_and_keys(self):
        updates = config()
        self.assertEqual(prepare({}, updates), updates)
        self.assertNotEqual(updates["llm"]["config"], updates["embedder"]["config"])

    def test_empty_and_masked_keys_are_omitted(self):
        for key in (None, "", "[redacted]"):
            out = prepare(config(), {"llm": {"config": {"api_key": key, "model": "custom"}}})
            self.assertNotIn("api_key", out["llm"]["config"])

    def test_changed_destination_needs_new_key(self):
        for updates in ({"provider": "gemini"}, {"config": {"openai_base_url": "https://new.test/v1"}}):
            with self.assertRaises(ValueError):
                prepare(config(), {"llm": updates})

    def test_changed_destination_with_explicit_key(self):
        out = prepare(
            config(), {"llm": {"config": {"openai_base_url": "http://localhost:8000/v1/", "api_key": "new-test"}}}
        )
        self.assertEqual(out["llm"]["config"]["openai_base_url"], "http://localhost:8000/v1")

    def test_reject_credential_urls_and_non_http(self):
        for url in (
            "file:///tmp/x",
            "https://user:secret@host/v1",
            "http://host/v1?key=secret",
            "http://host/#x",
            "http://host:bad",
            "https://",
            "http://ho st",
            123,
        ):
            with self.assertRaises(ValueError):
                provider_config.validate_base_url(url)

    def test_blank_endpoint_resets_official(self):
        out = prepare(config(), {"embedder": {"config": {"openai_base_url": "", "api_key": "official-test"}}})
        self.assertEqual(out["embedder"]["config"]["openai_base_url"], provider_config.OPENAI_URL)

    def test_dimensions(self):
        for dims in (0, -1, True, "1024"):
            with self.assertRaises(ValueError):
                prepare(config(), {"embedder": {"config": {"embedding_dims": dims}}})
        self.assertEqual(
            prepare(config(), {"embedder": {"config": {"embedding_dims": 1024}}})["embedder"]["config"][
                "embedding_dims"
            ],
            1024,
        )

    def test_input_not_mutated(self):
        old = config()
        updates = {"llm": {"config": {"api_key": "[redacted]"}}}
        prepare(old, updates)
        self.assertEqual(updates["llm"]["config"]["api_key"], "[redacted]")
        self.assertEqual(old, config())

    def test_pgvector_dimension_guards(self):
        base = {
            "vector_store": {
                "provider": "pgvector",
                "config": {"collection_name": "memories", "embedding_model_dims": 1536},
            }
        }
        import copy

        for dims in (2048, 1024):
            candidate = copy.deepcopy(base)
            candidate["embedder"] = {"config": {"embedding_dims": dims}}
            with self.assertRaises(ValueError):
                provider_config.validate_vector_dimensions(candidate, base)
        candidate = copy.deepcopy(base)
        candidate["vector_store"]["config"]["embedding_model_dims"] = 1024
        with self.assertRaises(ValueError):
            provider_config.validate_vector_dimensions(candidate, base)
        candidate["vector_store"]["config"]["collection_name"] = "new_memories"
        provider_config.validate_vector_dimensions(candidate, base)
        candidate["vector_store"]["config"]["embedding_model_dims"] = 2048
        with self.assertRaises(ValueError):
            provider_config.validate_vector_dimensions(candidate, base)

    def test_failed_runtime_update_is_atomic(self):
        fake_mem0 = ModuleType("mem0")
        fake_mem0.Memory = type("Memory", (), {"from_config": staticmethod(lambda _: object())})
        spec = importlib.util.spec_from_file_location("isolated_server_state", SERVER / "server_state.py")
        state = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"mem0": fake_mem0, "provider_config": provider_config}):
            spec.loader.exec_module(state)
        state.initialize_state(config())
        instance = state.get_memory_instance()
        with patch.object(fake_mem0.Memory, "from_config", side_effect=ValueError("private diagnostic")):
            with self.assertRaises(ValueError):
                state.update_config({"llm": {"config": {"model": "invalid"}}})
        self.assertEqual(state.get_current_config(), config())
        self.assertIs(state.get_memory_instance(), instance)
        with patch.object(state, "_save_overrides", side_effect=RuntimeError("Database unavailable")):
            with self.assertRaises(RuntimeError):
                state.update_config({"llm": {"config": {"model": "custom"}}})
        self.assertEqual(state.get_current_config(), config())
        self.assertIs(state.get_memory_instance(), instance)
        switched = {"llm": {"provider": "gemini", "config": {"api_key": "new-test", "model": "gemini-test"}}}
        merged = state._merge_config(config(), switched)
        self.assertEqual(merged["llm"], switched["llm"])


if __name__ == "__main__":
    unittest.main()
