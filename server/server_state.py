import json
import logging
import os
import threading
from copy import deepcopy
from typing import Any, Callable, Dict

from provider_config import prepare_provider_updates, validate_vector_dimensions

from mem0 import Memory

_state_lock = threading.RLock()
_current_config: Dict[str, Any] = {}
_memory_instance: Memory | None = None
_session_factory: Callable | None = None
_runtime_status = {"status": "needs_configuration", "ready": False, "missing_providers": [], "error_code": None}


class MemoryNotReadyError(RuntimeError):
    """Control plane is available, but model runtime is not ready."""


def _missing_credentials(config):
    env_keys = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GOOGLE_API_KEY"}
    return [
        name
        for name in ("llm", "embedder")
        if config.get(name, {}).get("provider") in env_keys
        and not (
            config.get(name, {}).get("config", {}).get("api_key") or os.environ.get(env_keys[config[name]["provider"]])
        )
    ]


def get_runtime_status():
    with _state_lock:
        return deepcopy(_runtime_status)


def set_session_factory(factory: Callable) -> None:
    global _session_factory
    _session_factory = factory


def _load_overrides() -> Dict[str, Any]:
    try:
        if _session_factory is None:
            return {}
        from models import Settings

        session = _session_factory()
        try:
            row = session.get(Settings, "config_overrides")
            if row is None:
                return {}
            return json.loads(row.value)
        finally:
            session.close()
    except Exception:
        raise RuntimeError("Could not load persisted provider configuration.") from None


def _save_overrides(overrides: Dict[str, Any]) -> None:
    try:
        if _session_factory is None:
            return
        from models import Settings
        from sqlalchemy.dialects.postgresql import insert

        session = _session_factory()
        try:
            serialized = json.dumps(overrides)
            stmt = (
                insert(Settings)
                .values(key="config_overrides", value=serialized)
                .on_conflict_do_update(
                    index_elements=[Settings.key],
                    set_={"value": serialized},
                )
            )
            session.execute(stmt)
            session.commit()
        finally:
            session.close()
    except Exception:
        logging.warning("Failed to persist config overrides to database")
        raise RuntimeError("Could not persist provider configuration.") from None


def _merge_config(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)

    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            if "provider" in value and value["provider"] != merged[key].get("provider"):
                merged[key] = deepcopy(value)
            else:
                merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value

    return merged


def initialize_state(default_config: Dict[str, Any]) -> None:
    global _current_config, _memory_instance, _runtime_status
    with _state_lock:
        _current_config = deepcopy(default_config)
        _memory_instance = None
        try:
            overrides = _load_overrides()
        except Exception:
            _runtime_status = {
                "status": "initialization_failed",
                "ready": False,
                "missing_providers": [],
                "error_code": "config_load_failed",
            }
            return
        if overrides:
            _current_config = _merge_config(_current_config, overrides)
        missing = _missing_credentials(_current_config)
        if missing:
            _runtime_status = {
                "status": "needs_configuration",
                "ready": False,
                "missing_providers": missing,
                "error_code": None,
            }
            return
        try:
            validate_vector_dimensions(_current_config)
            _memory_instance = Memory.from_config(_current_config)
        except Exception:
            # Keep authentication/configuration available, without exposing exception secrets.
            _runtime_status = {
                "status": "initialization_failed",
                "ready": False,
                "missing_providers": [],
                "error_code": "runtime_initialization_failed",
            }
            return
        _runtime_status = {"status": "ready", "ready": True, "missing_providers": [], "error_code": None}


def update_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    global _current_config, _memory_instance, _runtime_status
    with _state_lock:
        updates = prepare_provider_updates(_current_config, updates)
        next_config = _merge_config(_current_config, updates)
        for section in ("llm", "embedder"):
            if section in updates and updates[section].get(
                "provider", _current_config.get(section, {}).get("provider")
            ) != _current_config.get(section, {}).get("provider"):
                next_config[section] = deepcopy(updates[section])
        if _missing_credentials(next_config):
            raise ValueError("Both LLM and embedding provider credentials are required.")
        validate_vector_dimensions(next_config, _current_config)
        # Build before replacing live state: invalid configuration must not poison it.
        try:
            next_instance = Memory.from_config(next_config)
        except Exception:
            if _memory_instance is None:
                _runtime_status = {
                    "status": "initialization_failed",
                    "ready": False,
                    "missing_providers": [],
                    "error_code": "runtime_initialization_failed",
                }
            raise
        overrides = _load_overrides()
        overrides = _merge_config(overrides, updates)
        for section in ("llm", "embedder"):
            if section in updates:
                overrides[section] = deepcopy(next_config[section])
        _save_overrides(overrides)
        _current_config = next_config
        _memory_instance = next_instance
        _runtime_status = {"status": "ready", "ready": True, "missing_providers": [], "error_code": None}
        return deepcopy(_current_config)


def get_current_config() -> Dict[str, Any]:
    with _state_lock:
        return deepcopy(_current_config)


def get_memory_instance() -> Memory:
    with _state_lock:
        if _memory_instance is None:
            raise MemoryNotReadyError("Configure LLM and embedding providers before using memory operations.")
        return _memory_instance
