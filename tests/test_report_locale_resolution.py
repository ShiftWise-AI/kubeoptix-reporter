"""Tests for resolving the report locale from the /system-settings API.

These tests exercise `src.api.fetch_report_locale`, which must be called
before report generation and must:
  * accept only the four supported BCP 47 locales;
  * reject a missing/empty/unsupported `language` value without any
    fallback, following the project's existing HTTPException error pattern;
  * surface an error (not a silent default) when /system-settings is
    unavailable.
"""

import sys
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.api as api  # noqa: E402

SUPPORTED_LOCALES = ("pt-BR", "en-US", "es-ES", "it-IT")


_RealAsyncClient = httpx.AsyncClient


class _StubAsyncClient:
    """Drop-in stand-in for httpx.AsyncClient bound to a fixed transport."""

    def __init__(self, handler, *_, **__):
        self._client = _RealAsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://configurations-api:8000"
        )

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, *exc_info):
        await self._client.aclose()


def _patch_client(monkeypatch, handler):
    monkeypatch.setattr(api.httpx, "AsyncClient", lambda *a, **kw: _StubAsyncClient(handler))


def _settings_handler(payload=None, status_code=200):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system-settings"
        if payload is None:
            return httpx.Response(status_code)
        return httpx.Response(status_code, json=payload)

    return handler


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
@pytest.mark.asyncio
async def test_fetch_report_locale_accepts_each_supported_locale(monkeypatch, locale):
    _patch_client(monkeypatch, _settings_handler({"language": locale}))
    assert await api.fetch_report_locale() == locale


@pytest.mark.asyncio
async def test_fetch_report_locale_rejects_unsupported_language(monkeypatch):
    _patch_client(monkeypatch, _settings_handler({"language": "fr-FR"}))
    with pytest.raises(HTTPException) as exc_info:
        await api.fetch_report_locale()
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_report_locale_rejects_missing_language_field(monkeypatch):
    _patch_client(monkeypatch, _settings_handler({}))
    with pytest.raises(HTTPException) as exc_info:
        await api.fetch_report_locale()
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_report_locale_rejects_empty_language_field(monkeypatch):
    _patch_client(monkeypatch, _settings_handler({"language": ""}))
    with pytest.raises(HTTPException) as exc_info:
        await api.fetch_report_locale()
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_report_locale_raises_when_system_settings_unavailable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_client(monkeypatch, handler)
    with pytest.raises(HTTPException) as exc_info:
        await api.fetch_report_locale()
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_fetch_report_locale_raises_when_system_settings_returns_error_status(monkeypatch):
    _patch_client(monkeypatch, _settings_handler({"language": "pt-BR"}, status_code=500))
    with pytest.raises(HTTPException) as exc_info:
        await api.fetch_report_locale()
    assert exc_info.value.status_code == 503
