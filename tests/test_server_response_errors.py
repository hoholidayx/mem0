"""Offline API error-path regression tests; no provider requests or real secrets."""
import importlib.util
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location("isolated_server_errors", Path(__file__).parents[1] / "server/errors.py")
errors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(errors)


class ResponseFailure(Exception):
    def __init__(self, code):
        self.error_code = code
        super().__init__("PRIVATE_RESPONSE secret-test-key https://example.test/?secret=x")


@pytest.mark.parametrize("code", ["llm_response_truncated", "llm_empty_response", "llm_invalid_json", "llm_invalid_response"])
def test_response_errors_use_existing_502_path_without_secret_leak(code, caplog):
    app = FastAPI()
    app.add_exception_handler(errors.UpstreamError, errors.upstream_error_handler)

    @app.post("/memories")
    def add():
        token = errors.request_id_var.set("test-request-id")
        try:
            try:
                raise ResponseFailure(code)
            except Exception:
                raise errors.upstream_error() from None
        finally:
            errors.request_id_var.reset(token)

    with patch.dict(sys.modules, {"server_state": SimpleNamespace(MemoryNotReadyError=type("NotReady", (Exception,), {}))}):
        with caplog.at_level(logging.ERROR):
            response = TestClient(app).post("/memories")
    assert response.status_code == 502
    assert response.json()["code"] == code
    assert response.json()["request_id"] == "test-request-id"
    assert response.headers["x-request-id"] == "test-request-id"
    for secret in ("PRIVATE_RESPONSE", "secret-test-key", "secret=x"):
        assert secret not in response.text
        assert secret not in caplog.text


def test_wrapped_response_and_upstream_auth_failures_are_classified():
    inner = ResponseFailure("llm_response_truncated")
    outer = RuntimeError("safe wrapper")
    outer.__cause__ = inner
    assert errors._classify(outer)[0] == "llm_response_truncated"
    auth = Exception("sensitive provider body")
    auth.status_code = 401
    outer.__cause__ = auth
    assert errors._classify(outer)[0] == "provider_auth_failed"
