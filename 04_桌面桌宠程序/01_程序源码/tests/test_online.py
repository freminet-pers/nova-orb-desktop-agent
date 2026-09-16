import json
import threading
import unittest
from datetime import date, timedelta

from coco.online import OnlineCancelled, OnlineIntent, classify_online_request, fetch_weather, search_web


class Response:
    def __init__(self, value, status=200):
        self.data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.status = status

    def getcode(self):
        return self.status

    def read(self, limit=-1):
        return self.data if limit < 0 else self.data[:limit]

    def close(self):
        pass


class Opener:
    def __init__(self, values):
        self.values = list(values)
        self.urls = []

    def open(self, request, timeout=0):
        self.urls.append(request.full_url)
        return Response(self.values.pop(0))


class HeaderOpener(Opener):
    def __init__(self, values):
        super().__init__(values)
        self.headers = []

    def open(self, request, timeout=0):
        self.headers.append(dict(request.headers))
        return super().open(request, timeout)


class OnlineTests(unittest.TestCase):
    def test_classify_only_explicit_requests(self):
        weather = classify_online_request("查北京明天天气")
        self.assertEqual(weather, OnlineIntent("weather", "北京", 1))
        self.assertEqual(classify_online_request("北京今天会下雨吗").query, "北京")
        self.assertEqual(classify_online_request("weather in Tokyo tomorrow").query, "Tokyo")
        search = classify_online_request("搜索 Python 3.13 新特性")
        self.assertEqual(search.kind, "search")
        self.assertEqual(search.query, "Python 3.13 新特性")
        self.assertIsNone(classify_online_request("今天我想和你聊天"))
        self.assertIsNone(classify_online_request("Saturday 是星期六"))

    def test_weather_uses_city_local_daily_date_and_source(self):
        today = date.today()
        geo = {"results": [{"name": "北京", "latitude": 39.9, "longitude": 116.4,
                             "timezone": "Asia/Shanghai", "country": "中国", "admin1": "北京市",
                             "population": 10_000_000}]}
        forecast = {"daily": {"time": [(today + timedelta(days=i)).isoformat() for i in range(3)],
                              "weather_code": [0, 61, 3],
                              "temperature_2m_min": [10, 11, 12],
                              "temperature_2m_max": [20, 21, 22],
                              "precipitation_sum": [0, 2.5, 0.1],
                              "precipitation_probability_max": [1, 70, 20]}}
        opener = Opener([geo, forecast])
        result = fetch_weather(OnlineIntent("weather", "北京", 1), opener=opener)
        self.assertTrue(result.success)
        self.assertIn((today + timedelta(days=1)).isoformat(), result.text)
        self.assertIn("最低 11", result.text)
        self.assertIn("Open-Meteo", result.text)
        self.assertEqual(len(opener.urls), 2)
        self.assertNotIn("history", opener.urls[0])

    def test_search_summary_is_explicitly_limited_or_full_provider(self):
        data = {"AbstractText": "Python 是一种通用编程语言。", "AbstractURL": "https://python.org/", "RelatedTopics": []}
        result = search_web(OnlineIntent("search", "Python"), opener=Opener([data]))
        self.assertTrue(result.success)
        self.assertIn("即时摘要", result.text)
        self.assertIn("不是完整网页结果列表", result.text)
        self.assertIn("https://python.org/", result.text)

    def test_optional_brave_provider_returns_real_web_results_without_echoing_key(self):
        data = {"web": {"results": [{"title": "Python", "description": "Official site", "url": "https://python.org/"}]}}
        opener = HeaderOpener([data])
        result = search_web(OnlineIntent("search", "Python"), api_key="fake-brave-key", opener=opener)
        self.assertTrue(result.success)
        self.assertIn("Brave Search API", result.text)
        self.assertIn("https://python.org/", result.text)
        self.assertEqual(opener.headers[0].get("X-subscription-token"), "fake-brave-key")
        self.assertNotIn("fake-brave-key", result.text)

    def test_cancel_before_network(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(OnlineCancelled):
            fetch_weather(OnlineIntent("weather", "北京", 1), opener=Opener([]), cancel_event=cancel)


if __name__ == "__main__":
    unittest.main()
