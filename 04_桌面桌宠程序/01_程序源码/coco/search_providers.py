"""Small, dependency-free adapters for Nova's web-search providers.

This module only builds requests and parses provider payloads.  It deliberately
does not perform network I/O; :mod:`coco.online` owns timeout, cancellation,
response-size and error handling.  Keeping provider details here makes it
harder for one provider's key or response shape to leak into another route.
"""
from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from typing import Any, Mapping


TAVILY_URL = "https://api.tavily.com/search"
TAVILY_DOCS = "https://docs.tavily.com/documentation/api-reference/endpoint/search"
TAVILY_SIGNUP = "https://app.tavily.com"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_DOCS = "https://api-dashboard.search.brave.com/api-reference/web/search/get"
SEARXNG_DOCS = "https://docs.searxng.org/dev/search_api.html"
DDG_URL = "https://api.duckduckgo.com/"
DDG_DOCS = "https://duckduckgo.com/api"
DEEPSEEK_NATIVE_SEARCH_URL = "https://api.deepseek.com/anthropic/v1/messages"
DEEPSEEK_NATIVE_SEARCH_DOCS = "https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/web/web-search-deepseek"
DEEPSEEK_NATIVE_SEARCH_MODEL = "deepseek-flash"


@dataclass(frozen=True)
class SearchRequest:
    """An HTTP request description consumed by ``online._open_json``."""

    provider: str
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None = None
    docs_url: str = ""


@dataclass(frozen=True)
class SearchItem:
    title: str
    url: str
    snippet: str
    source: str


@dataclass(frozen=True)
class ParsedSearch:
    items: tuple[SearchItem, ...]
    source_urls: tuple[str, ...]
    docs_url: str


def normalize_provider(provider: str | None, api_key: str = "") -> str:
    """Return a stable provider id without guessing a new key's owner.

    ``auto`` remains compatible with the original Nova behavior: a supplied
    key means Brave, while no key means DuckDuckGo Instant Answer.  The UI
    should pass ``tavily`` explicitly for a Tavily key.
    """
    value = str(provider or "auto").strip().lower().replace("-", "_")
    aliases = {
        "": "auto",
        "duckduckgo": "ddg",
        "duckduckgo_instant_answer": "ddg",
        "instant_answer": "ddg",
        "searx": "searxng",
    }
    value = aliases.get(value, value)
    if value == "auto":
        return "brave" if str(api_key or "").strip() else "ddg"
    if value in {"deepseek", "deepseek_native", "deepseek_web"}:
        return "deepseek_native"
    if value not in {"tavily", "brave", "searxng", "ddg"}:
        raise ValueError("不支持的联网搜索 provider")
    return value


def provider_docs(provider: str) -> str:
    return {
        "tavily": TAVILY_DOCS,
        "brave": BRAVE_DOCS,
        "searxng": SEARXNG_DOCS,
        "ddg": DDG_DOCS,
        "deepseek_native": DEEPSEEK_NATIVE_SEARCH_DOCS,
    }.get(normalize_provider(provider), "")


def provider_key_scope(provider: str, endpoint: str = "") -> str:
    """Return the DPAPI binding scope for a provider key.

    The Brave scope is intentionally the legacy endpoint used by existing
    installs.  SearXNG has no common authentication scheme, so an optional
    user-supplied endpoint is scoped to its origin/path and never shared with
    a hosted provider.
    """
    normalized = normalize_provider(provider)
    if normalized == "tavily":
        return TAVILY_URL
    if normalized == "brave":
        return BRAVE_URL
    if normalized == "ddg":
        return DDG_URL
    # The native route reuses the separately scoped DeepSeek chat credential.
    # It must not create a second copy under a generic search-key scope.
    if normalized == "deepseek_native":
        return ""
    value = str(endpoint or "").strip()
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.username or parsed.password:
        return ""
    # A query string could contain a secret; it is never part of a key scope.
    path = parsed.path.rstrip("/") or "/"
    try:
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return ""
    if not host:
        return ""
    authority = host.lower()
    if ":" in authority and not authority.startswith("["):
        authority = "[" + authority + "]"
    if port:
        authority += ":" + str(port)
    return urllib.parse.urlunsplit((parsed.scheme.lower(), authority, path, "", ""))


def _safe_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url[:2000]


def _clean_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def build_search_request(
    provider: str,
    query: str,
    api_key: str = "",
    endpoint: str = "",
    *,
    max_results: int = 5,
    model: str = "",
) -> SearchRequest:
    """Build a provider request without logging or interpolating the key."""
    normalized = normalize_provider(provider, api_key)
    query = _clean_text(query, 160)
    if not query:
        raise ValueError("搜索关键词不能为空")
    max_results = max(1, min(int(max_results), 10))
    key = str(api_key or "").strip()
    if normalized == "deepseek_native":
        if not key:
            raise ValueError("DeepSeek 原生联网搜索需要先保存上方的 DeepSeek API Key")
        # This is a bounded source-retrieval request, not a second unrestricted
        # chat turn.  The parser accepts only native result/citation blocks.
        payload = {
            "model": _clean_text(model or DEEPSEEK_NATIVE_SEARCH_MODEL, 120),
            "max_tokens": 1024,
            "messages": [{
                "role": "user",
                "content": [{"type": "text", "text": "Perform a web search for the query: " + query}],
            }],
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        }
        return SearchRequest(
            normalized,
            "POST",
            DEEPSEEK_NATIVE_SEARCH_URL,
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "x-api-key": key,
                "Authorization": "Bearer " + key,
                "anthropic-version": "2023-06-01",
            },
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            DEEPSEEK_NATIVE_SEARCH_DOCS,
        )
    if normalized == "tavily":
        if not key:
            raise ValueError("Tavily 搜索需要 API Key")
        payload = {
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        return SearchRequest(
            normalized,
            "POST",
            TAVILY_URL,
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
            },
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            TAVILY_DOCS,
        )
    if normalized == "brave":
        if not key:
            raise ValueError("Brave 搜索需要 API Key")
        params = urllib.parse.urlencode(
            {"q": query, "count": max_results, "search_lang": "zh", "safesearch": "moderate"}
        )
        return SearchRequest(
            normalized,
            "GET",
            BRAVE_URL + "?" + params,
            {"Accept": "application/json", "X-Subscription-Token": key},
            None,
            BRAVE_DOCS,
        )
    if normalized == "searxng":
        base = str(endpoint or "").strip()
        parsed = urllib.parse.urlsplit(base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("SearXNG 需要配置自托管实例的 HTTP(S) 地址")
        if parsed.username or parsed.password:
            raise ValueError("SearXNG endpoint 不能包含用户名或密码")
        try:
            host = parsed.hostname
            port = parsed.port
        except ValueError:
            raise ValueError("SearXNG endpoint 的端口无效") from None
        if not host:
            raise ValueError("SearXNG endpoint 的主机无效")
        authority = host
        if ":" in authority and not authority.startswith("["):
            authority = "[" + authority + "]"
        if port:
            authority += ":" + str(port)
        path = parsed.path.rstrip("/")
        if not path or path == "/":
            path = "/search"
        params = urllib.parse.urlencode(
            {"q": query, "format": "json", "language": "zh-CN", "pageno": 1, "safesearch": 1}
        )
        url = urllib.parse.urlunsplit((parsed.scheme, authority, path, params, ""))
        headers = {"Accept": "application/json"}
        # SearXNG has no standard API-key header.  Do not invent one or send a
        # user's key to an arbitrary instance; self-hosted auth belongs in the
        # endpoint's reverse proxy configuration.
        return SearchRequest(normalized, "GET", url, headers, None, SEARXNG_DOCS)
    params = urllib.parse.urlencode(
        {"q": query, "format": "json", "no_html": "1", "no_redirect": "1", "skip_disambig": "1"}
    )
    return SearchRequest(normalized, "GET", DDG_URL + "?" + params, {"Accept": "application/json"}, None, DDG_DOCS)


def _items_from_list(values: Any, source: str) -> list[SearchItem]:
    output: list[SearchItem] = []
    if not isinstance(values, list):
        return output
    for item in values:
        if not isinstance(item, dict):
            continue
        url = _safe_url(item.get("url") or item.get("link"))
        if not url:
            continue
        title = _clean_text(item.get("title") or item.get("name") or "未命名结果", 180)
        snippet = _clean_text(item.get("content") or item.get("snippet") or item.get("description"), 420)
        output.append(SearchItem(title or "未命名结果", url, snippet, source))
    return output


def parse_full_results(provider: str, data: Mapping[str, Any], limit: int = 5) -> ParsedSearch:
    """Parse only link results; provider-generated answer text is ignored."""
    normalized = normalize_provider(provider)
    if normalized == "tavily":
        items = _items_from_list(data.get("results"), "Tavily Search API")
        docs = TAVILY_DOCS
    elif normalized == "brave":
        web = data.get("web")
        items = _items_from_list(web.get("results") if isinstance(web, dict) else None, "Brave Search API")
        docs = BRAVE_DOCS
    elif normalized == "searxng":
        items = _items_from_list(data.get("results"), "SearXNG")
        docs = SEARXNG_DOCS
    elif normalized == "deepseek_native":
        blocks = data.get("content")
        citations: dict[str, str] = {}
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "text":
                    continue
                for citation in block.get("citations") or []:
                    if not isinstance(citation, dict):
                        continue
                    url = _safe_url(citation.get("url"))
                    snippet = _clean_text(citation.get("cited_text"), 420)
                    if url and snippet and url not in citations:
                        citations[url] = snippet
        items = []
        seen: set[str] = set()
        result_blocks = 0
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "web_search_tool_result":
                    continue
                result_blocks += 1
                for item in block.get("content") or []:
                    if not isinstance(item, dict) or item.get("type") != "web_search_result":
                        continue
                    url = _safe_url(item.get("url"))
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    title = _clean_text(item.get("title") or "未命名结果", 180)
                    items.append(SearchItem(title or "未命名结果", url, citations.get(url, ""), "DeepSeek 原生联网搜索"))
        if not result_blocks:
            raise ValueError("DeepSeek 没有返回原生搜索结果，已拒绝把模型文字当作网页来源")
        docs = DEEPSEEK_NATIVE_SEARCH_DOCS
    else:
        items = []
        docs = DDG_DOCS
    items = items[: max(1, min(int(limit), 10))]
    urls = tuple(dict.fromkeys([item.url for item in items] + ([docs] if docs else [])))
    return ParsedSearch(tuple(items), urls, docs)
