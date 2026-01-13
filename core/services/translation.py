import hashlib
import logging
from dataclasses import dataclass
from typing import Callable, Iterable

import requests
from django.conf import settings

from core.models import Service, ServiceCategory, TranslationCache

try:
    from argostranslate import translate as argos_translate
except Exception:  # pragma: no cover - optional dependency
    argos_translate = None

logger = logging.getLogger(__name__)

SUPPORTED_LANGS = getattr(
    settings,
    "SUPPORTED_UI_LANGS",
    ("en", "ru", "uk", "fr", "ar", "hi"),
)
DEFAULT_SOURCE_LANG = "en"
MAX_TEXT_LENGTH = 1200  # guardrail for large descriptions
MAX_ITEMS_PER_BATCH = 50
REMOTE_FALLBACK_ENABLED = getattr(settings, "TRANSLATION_REMOTE_FALLBACK", True)
REMOTE_FALLBACK_TIMEOUT = getattr(settings, "TRANSLATION_REMOTE_TIMEOUT", 5)

_TRANSLATOR_CACHE: dict[tuple[str, str], Callable[[str], str] | None] = {}
_MISSING_TRANSLATORS: set[tuple[str, str]] = set()


def normalize_lang(lang: str | None) -> str:
    code = (lang or "").strip().lower()
    if not code:
        return DEFAULT_SOURCE_LANG
    code = code.split("-")[0]
    return code if code in SUPPORTED_LANGS else DEFAULT_SOURCE_LANG


def _hash_text(text: str) -> str:
    normalized = (text or "").strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _trim_text(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    if len(value) <= MAX_TEXT_LENGTH:
        return value
    # avoid chopping in the middle of a word
    return value[:MAX_TEXT_LENGTH].rsplit(" ", 1)[0].strip()


def _get_argos_translator(src_lang: str, target_lang: str) -> Callable[[str], str] | None:
    """
    Returns a callable translate(text) or None if no offline model is installed.
    No network calls are made here; argostranslate uses locally installed models.
    """
    if not argos_translate:
        return None

    key = (src_lang, target_lang)
    if key in _TRANSLATOR_CACHE:
        return _TRANSLATOR_CACHE[key]
    if key in _MISSING_TRANSLATORS:
        return None

    try:
        languages = argos_translate.load_installed_languages()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to load Argos Translate languages")
        _MISSING_TRANSLATORS.add(key)
        _TRANSLATOR_CACHE[key] = None
        return None

    def pick(code: str):
        return next((lang for lang in languages if lang.code.lower().startswith(code)), None)

    src = pick(src_lang)
    dest = pick(target_lang)
    if not src or not dest:
        _MISSING_TRANSLATORS.add(key)
        _TRANSLATOR_CACHE[key] = None
        return None

    try:
        translation = src.get_translation(dest)
    except Exception:
        logger.exception("Failed to build translation pipeline %s -> %s", src_lang, target_lang)
        _MISSING_TRANSLATORS.add(key)
        _TRANSLATOR_CACHE[key] = None
        return None

    if not translation:
        _MISSING_TRANSLATORS.add(key)
        _TRANSLATOR_CACHE[key] = None
        return None

    fn = translation.translate
    _TRANSLATOR_CACHE[key] = fn
    return fn


@dataclass(frozen=True)
class _TextItem:
    key: str
    text: str
    source_hash: str


def _build_items(texts: Iterable[tuple[str, str]]) -> list[_TextItem]:
    items: list[_TextItem] = []
    for key, value in texts or []:
        trimmed = _trim_text(value)
        if not trimmed:
            continue
        source_hash = _hash_text(trimmed)
        if not source_hash:
            continue
        items.append(_TextItem(key=key, text=trimmed, source_hash=source_hash))
    return items


def _translate_batch(items: list[_TextItem], target_lang: str) -> dict[str, str]:
    """
    Translate a batch of items using an offline Argos model.
    """
    translator = _get_argos_translator(DEFAULT_SOURCE_LANG, target_lang)
    translated: dict[str, str] = {}
    if translator:
        for item in items:
            try:
                result = translator(item.text)
            except Exception:
                logger.warning("Translation failed for key=%s", item.key, exc_info=True)
                continue
            if not result:
                continue
            translated[item.source_hash] = str(result).strip()

    if translated or not REMOTE_FALLBACK_ENABLED:
        return translated

    # Fallback to a lightweight, network-based translator (Google public endpoint).
    for item in items:
        try:
            resp = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={
                    "client": "gtx",
                    "sl": DEFAULT_SOURCE_LANG,
                    "tl": target_lang,
                    "dt": "t",
                    "q": item.text,
                },
                timeout=REMOTE_FALLBACK_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            translated_value = data[0][0][0] if data and data[0] and data[0][0] else ""
            if translated_value:
                translated[item.source_hash] = str(translated_value).strip()
        except Exception:
            logger.warning("Remote translation failed for key=%s", item.key, exc_info=True)
            continue

    return translated


def translate_texts(texts: Iterable[tuple[str, str]], target_lang: str) -> dict[str, str]:
    """
    Translate an iterable of (key, text) pairs. Returns key -> translated text.
    Uses TranslationCache to avoid repeated computation and to invalidate when source changes.
    """
    lang = normalize_lang(target_lang)
    if lang == DEFAULT_SOURCE_LANG:
        return {}

    items = _build_items(texts)
    if not items:
        return {}

    hashes = [item.source_hash for item in items]
    cached = {
        entry.source_hash: entry.translated_text
        for entry in TranslationCache.objects.filter(language=lang, source_hash__in=hashes)
    }

    # Deduplicate missing hashes before calling translator.
    missing: list[_TextItem] = []
    seen_missing = set()
    for item in items:
        if item.source_hash in cached or item.source_hash in seen_missing:
            continue
        seen_missing.add(item.source_hash)
        missing.append(item)

    if missing:
        for start in range(0, len(missing), MAX_ITEMS_PER_BATCH):
            chunk = missing[start:start + MAX_ITEMS_PER_BATCH]
            translated_chunk = _translate_batch(chunk, lang)
            if not translated_chunk:
                continue
            new_entries = []
            for item in chunk:
                translated_value = translated_chunk.get(item.source_hash)
                if not translated_value:
                    continue
                cached[item.source_hash] = translated_value
                new_entries.append(
                    TranslationCache(
                        language=lang,
                        source_language=DEFAULT_SOURCE_LANG,
                        source_hash=item.source_hash,
                        source_text=item.text,
                        translated_text=translated_value,
                    )
                )
            if new_entries:
                try:
                    TranslationCache.objects.bulk_create(new_entries, ignore_conflicts=True)
                except Exception:
                    logger.exception("Failed to persist translation cache batch")

    return {
        item.key: cached.get(item.source_hash, "")
        for item in items
        if item.source_hash in cached
    }


def translate_services(services: Iterable[Service], target_lang: str) -> dict[str, dict[str, str]]:
    """
    Translate user-facing fields for the provided services.
    Returns mapping: service_id -> {"name": ..., "description": ..., "category": ...}
    """
    services = list(services or [])
    lang = normalize_lang(target_lang)
    if not services or lang == DEFAULT_SOURCE_LANG:
        return {}

    text_pairs = []
    for srv in services:
        sid = str(getattr(srv, "id", "")) or ""
        if not sid:
            continue
        name = getattr(srv, "name", "") or ""
        desc = getattr(srv, "description", "") or ""
        cat_name = getattr(getattr(srv, "category", None), "name", "") or ""
        if name:
            text_pairs.append((f"{sid}:name", name))
        if desc:
            text_pairs.append((f"{sid}:description", desc))
        if cat_name:
            text_pairs.append((f"category:{getattr(srv, 'category_id', '') or cat_name}", cat_name))

    translated = translate_texts(text_pairs, lang)
    output: dict[str, dict[str, str]] = {}
    for srv in services:
        sid = str(getattr(srv, "id", ""))
        if not sid:
            continue
        entry = {}
        name_key = f"{sid}:name"
        desc_key = f"{sid}:description"
        cat_key = f"category:{getattr(srv, 'category_id', '') or (getattr(getattr(srv, 'category', None), 'name', '') or '')}"
        if name_key in translated:
            entry["name"] = translated[name_key]
        if desc_key in translated:
            entry["description"] = translated[desc_key]
        if cat_key in translated:
            entry["category"] = translated[cat_key]
        if entry:
            output[sid] = entry
    return output


def translate_categories(categories: Iterable[ServiceCategory], target_lang: str) -> dict[str, dict[str, str]]:
    """
    Translate category names. Returns mapping: category_id -> {"name": ...}
    """
    categories = list(categories or [])
    lang = normalize_lang(target_lang)
    if not categories or lang == DEFAULT_SOURCE_LANG:
        return {}

    pairs = []
    for cat in categories:
        cid = str(getattr(cat, "id", "")) or getattr(cat, "pk", "")
        name = getattr(cat, "name", "") or ""
        if cid and name:
            pairs.append((f"category:{cid}", name))
    translated = translate_texts(pairs, lang)
    output: dict[str, dict[str, str]] = {}
    for cat in categories:
        cid = str(getattr(cat, "id", "")) or getattr(cat, "pk", "")
        if not cid:
            continue
        name_key = f"category:{cid}"
        if name_key in translated:
            output[cid] = {"name": translated[name_key]}
    return output
