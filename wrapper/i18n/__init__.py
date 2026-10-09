"""Centralized i18n support for the generated report.

Supported locales follow BCP 47 and are intentionally restricted to the four
languages the report must be able to render in. Each locale has its own
message catalog module (``pt_br``, ``en_us``, ``es_es``, ``it_it``) so
translations stay grouped by locale instead of scattered across the
Markdown/AsciiDoc generation code.
"""

from datetime import datetime

from . import en_us, es_es, it_it, pt_br

SUPPORTED_LOCALES: tuple[str, ...] = ("pt-BR", "en-US", "es-ES", "it-IT")

_CATALOGS: dict[str, dict] = {
    "pt-BR": pt_br.MESSAGES,
    "en-US": en_us.MESSAGES,
    "es-ES": es_es.MESSAGES,
    "it-IT": it_it.MESSAGES,
}


class UnsupportedLocaleError(ValueError):
    """Raised when a locale is missing or not one of the supported BCP 47 locales."""


def validate_locale(language: str | None) -> str:
    """Validate a BCP 47 locale against the supported locale list.

    No fallback is applied: an unsupported, missing or empty value raises
    ``UnsupportedLocaleError`` instead of silently choosing another locale.
    """
    if not language:
        raise UnsupportedLocaleError(
            "Locale não informado: o campo 'language' de /system-settings está "
            "ausente ou vazio"
        )
    if language not in SUPPORTED_LOCALES:
        raise UnsupportedLocaleError(
            f"Locale não suportado: '{language}'. Locales suportados: "
            f"{', '.join(SUPPORTED_LOCALES)}"
        )
    return language


def _catalog(locale: str) -> dict:
    try:
        return _CATALOGS[locale]
    except KeyError as exc:
        raise UnsupportedLocaleError(
            f"Locale não suportado: '{locale}'. Locales suportados: "
            f"{', '.join(SUPPORTED_LOCALES)}"
        ) from exc


def translate(locale: str, key: str) -> str:
    """Return the top-level catalog entry (e.g. 'toc_title') for a locale."""
    return _catalog(locale)[key]


def format_document_date(locale: str, when: datetime) -> str:
    catalog = _catalog(locale)
    month_name = catalog["months"][when.month - 1]
    return catalog["document_date_format"].format(month=month_name, year=when.year)


def render_participants_template(locale: str, customer: str) -> str:
    messages = _catalog(locale)["participants"]
    header = f"| {messages['col_name']} | {messages['col_role']} | {messages['col_email']} | "
    separator = "| --- | --- | --- | "
    content = (
        f"# {messages['heading']}\n\n"
        f"## {messages['provider_heading']}\n"
        f"{header}\n{separator}\n"
        f"| <autors.name> | <authors.position> | <autors.email> | \n\n\n"
        f"## <documents.customer>\n"
        f"{header}\n{separator}\n"
        f"| <costumers_list.name> | <costumers_list.position> | <costumers_list.email> | \n\n\n"
    )
    return content.replace("<documents.customer>", customer)


def render_version_history_template(locale: str) -> str:
    messages = _catalog(locale)["version_history"]
    header = (
        f"| {messages['col_version']} | {messages['col_date']} | "
        f"{messages['col_contribution']} | {messages['col_role']} | "
        f"{messages['col_description']} |"
    )
    separator = "| --- | --- | --- | --- | --- |"
    row = (
        "| <versions.version_number> | <versions.created_at> | <authors.name> | "
        "<authors.position> | <version.description> |"
    )
    return f"# {messages['heading']}\n\n{header}\n{separator}\n{row}\n"


def render_terms_markdown(locale: str) -> str:
    messages = _catalog(locale)["terms"]
    paragraphs = "\n\n".join(messages["paragraphs"])
    return f"# {messages['heading']}\n\n{paragraphs}\n"


__all__ = [
    "SUPPORTED_LOCALES",
    "UnsupportedLocaleError",
    "validate_locale",
    "translate",
    "format_document_date",
    "render_participants_template",
    "render_version_history_template",
    "render_terms_markdown",
]
