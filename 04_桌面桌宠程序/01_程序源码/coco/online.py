"""Small, explicit online routes for Nova.

The model never receives a network tool.  The UI classifies a narrow weather
or search request and runs this module in a worker.  Only the city or query is
sent to the public endpoint; chat history, notes and API keys stay local.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .search_providers import (
    BRAVE_DOCS,
    BRAVE_URL,
    DDG_DOCS,
    DDG_URL,
    DEEPSEEK_NATIVE_SEARCH_DOCS,
    SEARXNG_DOCS,
    TAVILY_DOCS,
    TAVILY_SIGNUP,
    build_search_request,
    normalize_provider,
    parse_full_results,
    provider_key_scope,
)


GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_DOCS = "https://open-meteo.com/en/docs"
MAX_QUERY_CHARS = 160
MAX_BODY_BYTES = 1_000_000


class OnlineError(RuntimeError):
    """A safe, user-facing network failure without response/key contents."""


class OnlineCancelled(OnlineError):
    pass


@dataclass(frozen=True)
class OnlineIntent:
    kind: str
    query: str
    day_offset: int = 1


@dataclass(frozen=True)
class SearchConfig:
    """Provider selection passed from the UI without exposing key contents."""

    provider: str = "auto"
    api_key: str = ""
    endpoint: str = ""
    model: str = ""
    deepseek_api_key: str = ""


@dataclass(frozen=True)
class OnlineResult:
    success: bool
    text: str
    kind: str
    source_urls: tuple[str, ...] = ()


_WEATHER_WORDS = re.compile(
    r"天气|气温|温度|预报|降雨|下雨|weather|forecast|temperature|rain|snow",
    re.IGNORECASE,
)
_SEARCH_PREFIX = re.compile(
    r"^(?:请帮我|帮我|请|网上|在线)?\s*(?:搜索|搜一下|搜搜|查一下|查找|查询|查|search(?:\s+for)?|look\s+up)\s*",
    re.IGNORECASE,
)
_DATE_WORDS = ("今天", "明天", "后天", "today", "tomorrow", "the day after tomorrow")
_WEATHER_FILLERS = (
    "天气怎么样", "天气如何", "天气吗", "天气呢", "天气", "气温怎么样", "气温如何",
    "气温", "温度怎么样", "温度如何", "温度", "预报", "会不会下雨", "下雨吗", "降雨", "会", "吗", "呢",
    "weather", "forecast", "temperature", "rain", "snow",
)
_COMMAND_WORDS = (
    "请帮我", "帮我", "请问", "告诉我", "我想知道", "查一下", "查询", "看看", "查", "请",
)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n，,。！？?!")


def _remove_tokens(value: str, tokens) -> str:
    result = value
    for token in sorted(tokens, key=len, reverse=True):
        result = re.sub(re.escape(token), " ", result, flags=re.IGNORECASE)
    return _clean(result)


def _weather_city(text: str) -> str:
    value = _clean(text)
    # English requests have an unambiguous boundary after in/for.
    match = re.search(
        r"(?:weather|forecast|temperature|rain|snow)\s+(?:in|for)\s+(.+)$",
        value,
        flags=re.IGNORECASE,
    )
    if match:
        candidate = match.group(1)
    else:
        candidate = value
    candidate = _remove_tokens(candidate, _COMMAND_WORDS + _DATE_WORDS + _WEATHER_FILLERS)
    candidate = re.sub(r"\b(?:in|for|on)\b", " ", candidate, flags=re.IGNORECASE)
    return _clean(candidate)[:60]


def _search_query(text: str) -> str:
    value = _SEARCH_PREFIX.sub("", _clean(text), count=1)
    return _clean(value)[:MAX_QUERY_CHARS]


def classify_online_request(text: str) -> OnlineIntent | None:
    """Classify only explicit weather/search requests; ordinary chat is None."""
    value = _clean(text)
    if not value:
        return None
    if _WEATHER_WORDS.search(value):
        day_offset = 2 if re.search(r"后天|day after tomorrow", value, re.IGNORECASE) else 0 if re.search(r"今天|today", value, re.IGNORECASE) else 1
        return OnlineIntent("weather", _weather_city(value), day_offset)
    if _SEARCH_PREFIX.search(value):
        query = _search_query(value)
        return OnlineIntent("search", query, 0) if query else None
    return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise OnlineError("联网地址发生重定向，已停止请求")


def _cancelled(cancel_event):
    return cancel_event is not None and cancel_event.is_set()


def _open_json(url: str, cancel_event=None, opener=None, headers=None, timeout=8, method="GET", body=None):
    if _cancelled(cancel_event):
        raise OnlineCancelled("联网请求已取消")
    request = urllib.request.Request(
        url,
        data=body,
        method=str(method or "GET").upper(),
        headers={"Accept": "application/json", "User-Agent": "Nova/2026.09 local assistant", **(headers or {})},
    )
    opener = opener or urllib.request.build_opener(_NoRedirect())
    response = None
    try:
        response = opener.open(request, timeout=timeout)
        status = int(response.getcode() or 0)
        body = response.read(MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        if code == 429:
            raise OnlineError("联网服务暂时限流，请稍后再试") from None
        if code in (402, 432):
            raise OnlineError("联网服务额度已用尽，请检查免费额度或稍后再试") from None
        if code in (401, 403):
            raise OnlineError("联网服务拒绝了请求") from None
        raise OnlineError(f"联网服务返回 HTTP {code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError) or "timed out" in str(exc).lower():
            raise OnlineError("联网请求超时，请稍后再试") from None
        raise OnlineError("暂时无法连接联网服务") from None
    finally:
        if response is not None:
            response.close()
    if status < 200 or status >= 300:
        raise OnlineError(f"联网服务返回 HTTP {status}")
    if len(body) > MAX_BODY_BYTES:
        raise OnlineError("联网响应过大，已停止读取")
    if _cancelled(cancel_event):
        raise OnlineCancelled("联网请求已取消")
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise OnlineError("联网响应不是有效 JSON") from None
    if not isinstance(result, dict):
        raise OnlineError("联网响应格式不受支持")
    return result


def _choose_location(results, city):
    if not results:
        return None
    key = _clean(city).casefold()
    exact = [item for item in results if _clean(item.get("name", "")).casefold() == key]
    candidates = exact or results
    return max(candidates, key=lambda item: int(item.get("population", 0) or 0))


def _location_label(location):
    parts = [location.get("name"), location.get("admin1"), location.get("country")]
    return " · ".join(dict.fromkeys(str(item).strip() for item in parts if str(item or "").strip()))


_WEATHER_CODES = {
    0: "晴", 1: "大致晴", 2: "局部多云", 3: "阴", 45: "雾", 48: "冻雾",
    51: "小毛毛雨", 53: "毛毛雨", 55: "较强毛毛雨", 56: "冻毛毛雨", 57: "较强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "较强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒", 80: "阵雨", 81: "中阵雨",
    82: "强阵雨", 85: "阵雪", 86: "强阵雪", 95: "雷雨", 96: "雷雨伴冰雹", 99: "强雷雨伴冰雹",
}


def fetch_weather(intent: OnlineIntent, opener=None, cancel_event=None) -> OnlineResult:
    if not intent.query:
        return OnlineResult(False, "请告诉我想查哪个城市的天气，例如“查北京明天天气”。", "weather")
    geo_params = urllib.parse.urlencode({"name": intent.query, "count": 5, "language": "zh", "format": "json"})
    geo_url = GEO_URL + "?" + geo_params
    try:
        geo = _open_json(geo_url, cancel_event, opener)
        location = _choose_location(geo.get("results") or [], intent.query)
        if not location:
            return OnlineResult(False, f"没有找到“{intent.query}”对应的城市，请补充省州或国家。", "weather", (geo_url, OPEN_METEO_DOCS))
        timezone_name = str(location.get("timezone") or "auto")
        forecast_params = urllib.parse.urlencode({
            "latitude": location.get("latitude"), "longitude": location.get("longitude"),
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
            "timezone": timezone_name, "forecast_days": max(3, intent.day_offset + 2),
        })
        forecast_url = FORECAST_URL + "?" + forecast_params
        forecast = _open_json(forecast_url, cancel_event, opener)
        daily = forecast.get("daily")
        if not isinstance(daily, dict) or not isinstance(daily.get("time"), list):
            raise OnlineError("天气服务没有返回日预报")
        target_date = datetime.strptime(str(daily["time"][0]), "%Y-%m-%d").date() + timedelta(days=int(intent.day_offset))
        try:
            index = [str(item) for item in daily["time"]].index(target_date.isoformat())
        except ValueError:
            raise OnlineError("天气服务没有返回目标日期的预报") from None
        def value(key, default="暂无"):
            values = daily.get(key)
            return values[index] if isinstance(values, list) and index < len(values) else default
        code = value("weather_code", "")
        condition = _WEATHER_CODES.get(int(code), "天气代码 " + str(code)) if str(code).strip() else "暂无"
        location_text = _location_label(location) or intent.query
        generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        answer = (
            f"{location_text} {target_date.isoformat()}（当地时间）天气：{condition}。\n"
            f"最低 {value('temperature_2m_min')} °C，最高 {value('temperature_2m_max')} °C；"
            f"降水量 {value('precipitation_sum')} mm，降水概率最高 {value('precipitation_probability_max')}%。\n"
            f"来源：Open-Meteo（获取时间 {generated}）\n{OPEN_METEO_DOCS}"
        )
        return OnlineResult(True, answer, "weather", (forecast_url, OPEN_METEO_DOCS))
    except OnlineCancelled:
        raise
    except OnlineError as exc:
        return OnlineResult(False, f"天气查询没有完成：{exc}", "weather", (OPEN_METEO_DOCS,))


def _flatten_topics(items, output=None):
    output = output if output is not None else []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if item.get("Text") and item.get("FirstURL"):
            output.append((str(item["Text"]).strip(), str(item["FirstURL"])))
        _flatten_topics(item.get("Topics"), output)
        if len(output) >= 3:
            break
    return output


def _search_full_provider(provider, query, api_key="", endpoint="", model="", opener=None, cancel_event=None) -> OnlineResult:
    """Query a full-result provider and render title/URL/snippet/source."""
    try:
        request = build_search_request(provider, query, api_key=api_key, endpoint=endpoint, max_results=5, model=model)
        data = _open_json(
            request.url,
            cancel_event,
            opener,
            headers=request.headers,
            method=request.method,
            body=request.body,
        )
        parsed = parse_full_results(request.provider, data, limit=5)
        if not parsed.items:
            return OnlineResult(False, f"没有找到“{query}”的网页结果。请换个关键词再试。", "search", (request.docs_url,))
        lines = [f"联网搜索：{query}"]
        for item in parsed.items:
            lines.append(f"· {item.title}")
            if item.snippet:
                lines.append("  " + item.snippet)
            lines.append("  " + item.url)
            lines.append("  来源：" + item.source)
        lines.append("说明：以上是搜索服务返回的网页结果；摘要仅供参考，请打开原网页核实。")
        lines.append(request.docs_url)
        return OnlineResult(True, "\n".join(lines), "search", parsed.source_urls)
    except OnlineCancelled:
        raise
    except ValueError as exc:
        return OnlineResult(False, f"网页搜索没有完成：{exc}", "search")
    except OnlineError as exc:
        docs = provider_key_scope(provider, endpoint) or provider
        return OnlineResult(False, f"网页搜索没有完成：{exc}", "search", (provider_docs_url(provider),))


def _search_brave(query, api_key, opener=None, cancel_event=None) -> OnlineResult:
    """Backward-compatible Brave adapter used by existing callers/tests."""
    return _search_full_provider("brave", query, api_key=api_key, opener=opener, cancel_event=cancel_event)


def provider_docs_url(provider: str) -> str:
    """Return a public docs link for error/source display."""
    try:
        return {
            "tavily": TAVILY_DOCS,
            "brave": BRAVE_DOCS,
            "searxng": SEARXNG_DOCS,
            "ddg": DDG_DOCS,
            "deepseek_native": DEEPSEEK_NATIVE_SEARCH_DOCS,
        }.get(normalize_provider(provider), "")
    except ValueError:
        return ""


def _search_ddg(query, opener=None, cancel_event=None) -> OnlineResult:
    """Keep the no-key route honest: DDG Instant Answer is not full search."""
    browser_url = "https://duckduckgo.com/?" + urllib.parse.urlencode({"q": query})
    try:
        request = build_search_request("ddg", query)
        data = _open_json(request.url, cancel_event, opener, headers=request.headers)
        abstract = str(data.get("AbstractText") or data.get("Answer") or data.get("Definition") or "").strip()
        source = str(data.get("AbstractURL") or data.get("DefinitionURL") or "").strip()
        topics = _flatten_topics(data.get("RelatedTopics"))
        if not abstract and not topics:
            return OnlineResult(False, f"没有找到“{query}”的可靠即时摘要。你可以在浏览器中继续查看：\n{browser_url}", "search", (browser_url, DDG_DOCS))
        lines = [f"联网搜索（即时摘要）：{query}"]
        if abstract:
            lines.append(abstract[:1800])
            if source:
                lines.append("来源：" + source)
        for text, url in topics:
            lines.append("· " + text[:320] + "\n  " + url)
        lines.append("说明：这是 DuckDuckGo Instant Answer 摘要，不是完整网页结果列表。")
        lines.append(DDG_DOCS)
        urls = tuple(dict.fromkeys(([source] if source else []) + [url for _, url in topics] + [DDG_DOCS]))
        return OnlineResult(True, "\n".join(lines), "search", urls)
    except OnlineCancelled:
        raise
    except OnlineError as exc:
        return OnlineResult(False, f"联网搜索没有完成：{exc}\n可在浏览器中查看：{browser_url}", "search", (browser_url, DDG_DOCS))


def _config_values(search_config=None, provider="auto", api_key="", endpoint=""):
    if isinstance(search_config, SearchConfig):
        return (
            search_config.provider, search_config.api_key, search_config.endpoint,
            search_config.model, search_config.deepseek_api_key,
        )
    if isinstance(search_config, dict):
        return (
            str(search_config.get("provider") or provider),
            str(search_config.get("api_key") or api_key),
            str(search_config.get("endpoint") or endpoint),
            str(search_config.get("model") or ""),
            str(search_config.get("deepseek_api_key") or ""),
        )
    return provider, api_key, endpoint, "", ""


def search_web(
    intent: OnlineIntent,
    api_key="",
    opener=None,
    cancel_event=None,
    provider="auto",
    endpoint="",
    search_config=None,
) -> OnlineResult:
    query = _clean(intent.query)[:MAX_QUERY_CHARS]
    if not query:
        return OnlineResult(False, "请告诉我想搜索的关键词。", "search")
    provider, api_key, endpoint, model, deepseek_api_key = _config_values(search_config, provider, api_key, endpoint)
    try:
        normalized = normalize_provider(provider, api_key)
    except ValueError as exc:
        return OnlineResult(False, f"网页搜索没有完成：{exc}", "search")
    if normalized == "ddg":
        return _search_ddg(query, opener=opener, cancel_event=cancel_event)
    if normalized == "tavily" and not str(api_key or "").strip():
        return OnlineResult(
            False,
            "Tavily 搜索需要 API Key；请先在官方页面注册并把 Key 配置到联网搜索设置中。不会自动使用其他 provider 的 Key。\n" + TAVILY_SIGNUP,
            "search",
            (TAVILY_SIGNUP, TAVILY_DOCS),
        )
    if normalized == "brave" and not str(api_key or "").strip():
        return OnlineResult(False, "Brave 搜索需要 API Key，请在联网搜索设置中配置。", "search", (BRAVE_DOCS,))
    if normalized == "searxng" and not str(endpoint or "").strip():
        return OnlineResult(
            False,
            "SearXNG 仅支持你配置的自托管实例；未配置 endpoint，不会把查询发送到未知公共实例。\n" + SEARXNG_DOCS,
            "search",
            (SEARXNG_DOCS,),
        )
    if normalized == "deepseek_native":
        api_key = deepseek_api_key
    return _search_full_provider(
        normalized,
        query,
        api_key=api_key,
        endpoint=endpoint,
        model=model,
        opener=opener,
        cancel_event=cancel_event,
    )


def fetch_online(
    intent: OnlineIntent,
    api_key="",
    opener=None,
    cancel_event=None,
    provider="auto",
    endpoint="",
    search_config=None,
) -> OnlineResult:
    if intent.kind == "weather":
        return fetch_weather(intent, opener=opener, cancel_event=cancel_event)
    if intent.kind == "search":
        return search_web(
            intent,
            api_key=api_key,
            opener=opener,
            cancel_event=cancel_event,
            provider=provider,
            endpoint=endpoint,
            search_config=search_config,
        )
    return OnlineResult(False, "暂不支持这个联网请求。", intent.kind)
