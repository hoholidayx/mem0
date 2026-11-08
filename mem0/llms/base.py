import json
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union

from mem0.configs.llms.base import BaseLlmConfig
from mem0.exceptions import LLMResponseError


class LLMBase(ABC):
    """
    Base class for all LLM providers.
    Handles common functionality and delegates provider-specific logic to subclasses.
    """

    def __init__(self, config: Optional[Union[BaseLlmConfig, Dict]] = None):
        """Initialize a base LLM class

        :param config: LLM configuration option class or dict, defaults to None
        :type config: Optional[Union[BaseLlmConfig, Dict]], optional
        """
        if config is None:
            self.config = BaseLlmConfig()
        elif isinstance(config, dict):
            # Handle dict-based configuration (backward compatibility)
            self.config = BaseLlmConfig(**config)
        else:
            self.config = config

        # Validate configuration
        self._validate_config()

    def _validate_config(self):
        """
        Validate the configuration.
        Override in subclasses to add provider-specific validation.
        """
        if not hasattr(self.config, "model"):
            raise ValueError("Configuration must have a 'model' attribute")

    def _is_reasoning_model(self, model: str) -> bool:
        """
        Check if the model is a reasoning model or GPT-5 series that doesn't support certain parameters.

        An explicit ``is_reasoning_model`` on the config takes precedence over the
        name-based heuristic. This lets deployments with custom/versioned model
        names (e.g. Azure ``gpt-5.4-nano-2026-03-17``) opt in or out without
        relying on string matching. When the config value is ``None`` (default),
        classification falls back to the name-based heuristic below.

        Args:
            model: The model name to check

        Returns:
            bool: True if the model is a reasoning model or GPT-5 series
        """
        explicit = getattr(self.config, "is_reasoning_model", None)
        if explicit is not None:
            return explicit

        reasoning_models = {
            "o1",
            "o1-preview",
            "o3-mini",
            "o3",
            "gpt-5",
            "gpt-5o",
            "gpt-5o-mini",
            "gpt-5o-micro",
        }

        model_lower = model.lower()
        # Strip provider prefixes (e.g. "openai/o3-mini" -> "o3-mini")
        base_model = model_lower.rsplit("/", 1)[-1]

        if base_model in reasoning_models:
            return True

        # Match o1/o3 family with prefixes (o1-2024-12-17, o3-2025-04-16)
        # but NOT gpt-5.x variants (gpt-5.4-mini supports temperature)
        if any(base_model.startswith(prefix) for prefix in ["o1-", "o1.", "o3-", "o3."]):
            return True

        return False

    def _uses_max_completion_tokens(self, model: str) -> bool:
        """
        Check if the model expects ``max_completion_tokens`` instead of ``max_tokens``.

        The whole GPT-5 family (gpt-5.4-mini, gpt-5.4-nano, gpt-5.5, ...) rejects the
        legacy ``max_tokens`` parameter on the Chat Completions API and requires
        ``max_completion_tokens``. Older models (gpt-4.x, gpt-3.5, etc.) still accept
        ``max_tokens``.

        Args:
            model: The model name to check

        Returns:
            bool: True if the model requires ``max_completion_tokens``
        """
        # Strip provider prefixes (e.g. "openai/gpt-5.4-mini" -> "gpt-5.4-mini")
        base_model = (model or "").lower().rsplit("/", 1)[-1]
        return base_model.startswith("gpt-5")

    def _get_supported_params(self, **kwargs) -> Dict:
        """
        Get parameters that are supported by the current model.
        Filters out unsupported parameters for reasoning models and GPT-5 series.

        Args:
            **kwargs: Additional parameters to include

        Returns:
            Dict: Filtered parameters dictionary
        """
        model = getattr(self.config, "model", "")

        if self._is_reasoning_model(model):
            supported_params = {}
            if self.config.max_tokens is not None:
                supported_params["max_completion_tokens"] = self.config.max_tokens

            if "messages" in kwargs:
                supported_params["messages"] = kwargs["messages"]
            if "response_format" in kwargs:
                supported_params["response_format"] = kwargs["response_format"]
            if "tools" in kwargs:
                supported_params["tools"] = kwargs["tools"]
            if "tool_choice" in kwargs:
                supported_params["tool_choice"] = kwargs["tool_choice"]

            # Add reasoning_effort if configured
            reasoning_effort = getattr(self.config, "reasoning_effort", None)
            if reasoning_effort:
                supported_params["reasoning_effort"] = reasoning_effort

            return supported_params
        else:
            # For regular models, include all common parameters
            return self._get_common_params(**kwargs)

    @abstractmethod
    def generate_response(
        self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None, tool_choice: str = "auto", **kwargs
    ):
        """
        Generate a response based on the given messages.

        Args:
            messages (list): List of message dicts containing 'role' and 'content'.
            tools (list, optional): List of tools that the model can call. Defaults to None.
            tool_choice (str, optional): Tool choice method. Defaults to "auto".
            **kwargs: Additional provider-specific parameters.

        Returns:
            str or dict: The generated response.
        """
        pass

    def _get_common_params(self, **kwargs) -> Dict:
        """
        Get common parameters that most providers use.

        Returns:
            Dict: Common parameters dictionary.
        """
        params = {
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
        }

        model = getattr(self.config, "model", "")
        if self.config.max_tokens is not None:
            key = "max_completion_tokens" if self._uses_max_completion_tokens(model) else "max_tokens"
            params[key] = self.config.max_tokens

        # Add provider-specific parameters from kwargs
        params.update(kwargs)

        return params

    @staticmethod
    def _check_finish_reason(reason):
        # Prefer enum names: older Gemini SDKs use numeric enum values.
        enum_name = getattr(reason, "name", None)
        reason = enum_name if isinstance(enum_name, str) else getattr(reason, "value", reason)
        if isinstance(reason, str) and reason.lower() in {
            "length",
            "max_tokens",
            "max_token",
            "max_output_tokens",
            "model_length",
            "max_tokens_reached",
            "max_length",
            "model_context_window_exceeded",
        }:
            raise LLMResponseError("LLM response was truncated.", error_code="llm_response_truncated")

    @staticmethod
    def _validate_response_content(content, tool_calls=None):
        if not tool_calls and (content is None or (isinstance(content, (str, list)) and not content)):
            raise LLMResponseError("LLM returned an empty response.", error_code="llm_empty_response")
        if not tool_calls and isinstance(content, str) and not content.strip():
            raise LLMResponseError("LLM returned an empty response.", error_code="llm_empty_response")

    def _validate_chat_response(self, response, tools=None):
        if not response.choices:
            raise LLMResponseError("LLM returned an empty response.", error_code="llm_empty_response")
        choice = response.choices[0]
        self._check_finish_reason(getattr(choice, "finish_reason", None))
        self._validate_response_content(
            choice.message.content, getattr(choice.message, "tool_calls", None) if tools else None
        )

    @staticmethod
    def _parse_tool_arguments(arguments):
        try:
            if isinstance(arguments, str):
                text = arguments.strip()
                if text.startswith("```json\n") and text.endswith("```"):
                    text = text[8:-3].strip()
                elif text.startswith("```\n") and text.endswith("```"):
                    text = text[4:-3].strip()
                parsed = json.loads(text)
            else:
                parsed = arguments
            if not isinstance(parsed, dict):
                raise ValueError("Tool arguments must be an object")
            return parsed
        except (ValueError, TypeError):
            raise LLMResponseError("LLM returned invalid tool arguments.", error_code="llm_invalid_response") from None
