"""Further reading from trusted health sources, found with the Tavily search API.

Not a model call: Tavily is a web-search API (``include_answer`` is always off, so Tavily generates no text).
Privacy and safety rules:

* Only a fixed **topic query** (from ``agent/references.py``) is sent, never the user's message.
* Results are restricted to an allowlist of public-health and professional-society sites per language
  (``include_domains``) and filtered again on the exact host (sub-domains such as sponsored sections are
  dropped).
* Snippets are shown to the user as quotations with their link. They are **never** passed to the language
  model (no prompt injection, no unreviewed medical claims in generated text).
* Results are cached per (topic, language) for 24 h to bound cost; failures return no references.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from nemotwins.config import get_settings

log = logging.getLogger("nemotwins.tavily")
URL = "https://api.tavily.com/search"
CACHE_TTL_S = 24 * 3600
MAX_RESULTS = 3
SNIPPET_CHARS = 280

# Reviewed allowlists (exact hosts; "www." is accepted for each). Public-health agencies, national health
# portals and diabetes professional societies. Checked to return results on 2026-10-08.
ALLOWLIST: dict[str, tuple[str, ...]] = {
    "en-US": ("who.int", "cdc.gov", "niddk.nih.gov", "medlineplus.gov", "nhs.uk", "diabetes.org"),
    "es-ES": ("who.int", "medlineplus.gov", "cdc.gov", "sanidad.gob.es", "paho.org", "sediabetes.org"),
    "fr-FR": ("who.int", "ameli.fr", "has-sante.fr", "santepubliquefrance.fr", "federationdesdiabetiques.org"),
    "de-DE": ("who.int", "gesundheitsinformation.de", "diabinfo.de", "gesund.bund.de", "diabetesde.org"),
    "it-IT": ("who.int", "iss.it", "epicentro.iss.it", "salute.gov.it", "siditalia.it"),
    "ja-JP": ("who.int", "mhlw.go.jp", "kennet.mhlw.go.jp", "e-healthnet.mhlw.go.jp", "jds.or.jp", "dmic.ncgm.go.jp"),
}

_CACHE: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_LOCK = threading.Lock()
STATS: dict[str, Any] = {"requests": 0, "cache_hits": 0, "errors": 0, "last_error": None}


def configured() -> bool:
    s = get_settings()
    return bool(s.references_enabled and s.tavily_api_key.strip())


def available() -> bool:
    """Live mode only: the offline demo never reaches the network."""
    return get_settings().live and configured()


def _host_ok(url: str, lang: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    bare = host[4:] if host.startswith("www.") else host
    return bare if bare in ALLOWLIST.get(lang, ALLOWLIST["en-US"]) else None


def _clean(text: str) -> str:
    text = " ".join((text or "").replace("\u00ad", "").split())
    return text if len(text) <= SNIPPET_CHARS else text[: SNIPPET_CHARS - 1].rsplit(" ", 1)[0] + "…"


def _strip_title(content: str, title: str) -> str:
    """Page extracts sometimes start with 'Title: <page title>'; the title is already shown as the link."""
    c = content.strip()
    if c.lower().startswith("title:"):
        c = c[6:].strip()
    if title and c.startswith(title.strip()):
        c = c[len(title.strip()):]
    return c.strip(" .|:-\n")


def search(topic: str, query: str, lang: str, timeout_s: float = 10.0) -> list[dict]:
    """[{title, url, domain, snippet}] from allowlisted hosts, or [] (never raises)."""
    if not available():
        return []
    key = (topic, lang)
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < CACHE_TTL_S:
            STATS["cache_hits"] += 1
            return [dict(x) for x in hit[1]]
    body = {"query": query, "search_depth": "basic", "max_results": 6, "include_answer": False,
            "include_raw_content": False, "include_images": False,
            "include_domains": list(ALLOWLIST.get(lang, ALLOWLIST["en-US"]))}
    try:
        STATS["requests"] += 1
        r = httpx.post(URL, json=body, timeout=timeout_s,
                       headers={"Authorization": f"Bearer {get_settings().tavily_api_key.strip()}"})
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}")
        results = r.json().get("results") or []
    except Exception as exc:  # noqa: BLE001 - further reading is optional; never break a reply
        STATS["errors"] += 1
        STATS["last_error"] = type(exc).__name__ if not isinstance(exc, RuntimeError) else str(exc)
        log.warning("tavily search failed for topic %s (%s): %s", topic, lang, STATS["last_error"])
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for x in results:
        url = str(x.get("url") or "")
        dom = _host_ok(url, lang)
        if not dom or url in seen or url.lower().endswith(".pdf"):
            continue
        seen.add(url)
        title = str(x.get("title") or dom)
        out.append({"title": _clean(title)[:140], "url": url, "domain": dom,
                    "snippet": _clean(_strip_title(str(x.get("content") or ""), title))})
        if len(out) >= MAX_RESULTS:
            break
    with _LOCK:
        _CACHE[key] = (now, out)
    return [dict(x) for x in out]


def status() -> dict:
    return {"enabled": configured(), "live": available(), "provider": "tavily", "kind": "web search API (no model)",
            "allowlist": {k: list(v) for k, v in ALLOWLIST.items()}, "stats": dict(STATS),
            "reason": None if configured() else "Set the Tavily key (TAVILY_API_KEY) and REFERENCES_ENABLED=true."}
