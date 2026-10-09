"""Unit tests for the report i18n catalog (wrapper.i18n)."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wrapper import i18n  # noqa: E402

SUPPORTED_LOCALES = i18n.SUPPORTED_LOCALES


def test_supported_locales_are_exactly_the_four_bcp47_locales():
    assert set(SUPPORTED_LOCALES) == {"pt-BR", "en-US", "es-ES", "it-IT"}


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_validate_locale_accepts_supported_locales(locale):
    assert i18n.validate_locale(locale) == locale


@pytest.mark.parametrize("language", [None, ""])
def test_validate_locale_rejects_missing_or_empty_language(language):
    with pytest.raises(i18n.UnsupportedLocaleError):
        i18n.validate_locale(language)


@pytest.mark.parametrize("language", ["fr-FR", "pt", "pt_BR", "PT-BR", "de-DE"])
def test_validate_locale_rejects_unsupported_locale(language):
    with pytest.raises(i18n.UnsupportedLocaleError):
        i18n.validate_locale(language)


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_render_participants_template_keeps_row_placeholders(locale):
    content = i18n.render_participants_template(locale, "Acme Corp")
    assert "<documents.customer>" not in content
    assert "Acme Corp" in content
    assert "<autors.name>" in content
    assert "<authors.position>" in content
    assert "<autors.email>" in content
    assert "<costumers_list.name>" in content
    assert "<costumers_list.position>" in content
    assert "<costumers_list.email>" in content


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_render_terms_contains_experimental_project_and_user_responsibility(locale):
    content = i18n.render_terms_markdown(locale)
    assert "ShiftWise AI" in content
    assert len(content.split("\n\n")) == 5


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_render_version_history_template_keeps_row_placeholders(locale):
    content = i18n.render_version_history_template(locale)
    assert "<versions.version_number>" in content
    assert "<versions.created_at>" in content
    assert "<authors.name>" in content
    assert "<authors.position>" in content
    assert "<version.description>" in content


def test_render_terms_are_localized():
    rendered = {
        locale: i18n.render_terms_markdown(locale)
        for locale in SUPPORTED_LOCALES
    }
    assert len(set(rendered.values())) == len(SUPPORTED_LOCALES)


@pytest.mark.parametrize(
    "locale,expected",
    [
        ("pt-BR", "Setembro de 2026"),
        ("en-US", "September 2026"),
        ("es-ES", "septiembre de 2026"),
        ("it-IT", "settembre 2026"),
    ],
)
def test_format_document_date_per_locale(locale, expected):
    assert i18n.format_document_date(locale, datetime(2026, 9, 20)) == expected


def test_translate_toc_figure_table_captions_are_locale_specific():
    captions = {
        locale: (
            i18n.translate(locale, "toc_title"),
            i18n.translate(locale, "figure_caption"),
            i18n.translate(locale, "table_caption"),
        )
        for locale in SUPPORTED_LOCALES
    }
    assert captions["pt-BR"] == ("Sumário", "Figura", "Tabela")
    assert captions["en-US"] == ("Table of Contents", "Figure", "Table")
    assert captions["es-ES"] == ("Índice", "Figura", "Tabla")
    assert captions["it-IT"] == ("Indice", "Figura", "Tabella")
