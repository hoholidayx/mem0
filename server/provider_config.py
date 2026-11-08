"""Validate provider updates without exposing or forwarding old credentials."""

from copy import deepcopy
from urllib.parse import urlsplit


class ProviderConfigError(ValueError):
    """Safe validation message containing no user credentials."""


OPENAI_URL = "https://api.openai.com/v1"


def validate_base_url(value):
    if value is None or value == "":
        return OPENAI_URL
    if not isinstance(value, str):
        raise ProviderConfigError("Base URL must be an HTTP or HTTPS URL.")
    value = value.strip().rstrip("/")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ProviderConfigError("Base URL must be a valid HTTP or HTTPS URL.") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(c.isspace() or ord(c) < 32 for c in value)
        or (port is not None and port < 1)
    ):
        raise ProviderConfigError("Base URL must use HTTP(S), without credentials, query parameters or fragments.")
    return value


def prepare_provider_updates(current, updates):
    """Blank keys preserve the same destination only; changed endpoints require a key."""
    result = deepcopy(updates)
    for section in ("llm", "embedder"):
        if section not in result:
            continue
        incoming = result[section]
        if not isinstance(incoming, dict):
            raise ProviderConfigError(f"{section} must be an object.")
        old = current.get(section, {})
        provider = incoming.get("provider", old.get("provider"))
        config = incoming.setdefault("config", {})
        if not isinstance(config, dict):
            raise ProviderConfigError(f"{section}.config must be an object.")
        key = config.get("api_key")
        if key in (None, "", "[redacted]"):
            config.pop("api_key", None)
            key = None
        elif not isinstance(key, str):
            raise ProviderConfigError(f"{section} API key must be a string.")
        previous = old.get("config", {})
        changed = provider != old.get("provider")
        if provider == "openai":
            old_url = validate_base_url(previous.get("openai_base_url"))
            new_url = validate_base_url(config.get("openai_base_url", old_url))
            config["openai_base_url"] = new_url
            changed = changed or new_url != old_url
        if changed and not key:
            raise ProviderConfigError(f"Enter a new {section} API key when changing its provider or Base URL.")
        if section == "llm" and "max_tokens" in config:
            limit = config["max_tokens"]
            if limit is not None and (type(limit) is not int or limit < 1):
                raise ProviderConfigError("LLM max tokens must be a positive integer or blank for no client limit.")
        if section == "embedder" and "embedding_dims" in config:
            dims = config["embedding_dims"]
            if dims is not None and (type(dims) is not int or dims < 1):
                raise ProviderConfigError("Embedding dimensions must be a positive integer.")
    return result


def validate_vector_dimensions(config, previous=None):
    vector = config.get("vector_store", {})
    if vector.get("provider") != "pgvector":
        return
    options = vector.get("config", {})
    dims = options.get("embedding_model_dims", 1536)
    if type(dims) is not int or dims < 1:
        raise ProviderConfigError("Vector dimensions must be a positive integer.")
    if options.get("hnsw", True) and dims > 2000:
        raise ProviderConfigError(
            "pgvector vector HNSW supports at most 2000 dimensions; 2048 requires a different index configuration."
        )
    if dims > 16000:
        raise ProviderConfigError("pgvector vector storage supports at most 16000 dimensions.")
    collection = options.get("collection_name")
    if collection is not None and (not isinstance(collection, str) or not collection.strip()):
        raise ProviderConfigError("Vector collection name must be a non-empty string.")
    embed_dims = config.get("embedder", {}).get("config", {}).get("embedding_dims")
    if embed_dims is not None and embed_dims != dims:
        raise ProviderConfigError(
            f"Embedding API dimensions ({embed_dims}) must match vector storage dimensions ({dims}). "
            "Set Vector storage dimensions in the form as well, and choose a new collection when changing dimensions."
        )
    if previous:
        old = previous.get("vector_store", {}).get("config", {})
        if dims != old.get("embedding_model_dims", 1536) and options.get("collection_name") == old.get(
            "collection_name"
        ):
            raise ProviderConfigError(
                "Changing vector dimensions requires a new collection name; existing vectors are not migrated automatically."
            )
