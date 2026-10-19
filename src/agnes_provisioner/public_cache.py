from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import Error as BrowserError


@dataclass
class Asset:
    body: bytes
    headers: dict[str, str]
    expires: float


class PublicAssetCache:
    """Share publicly cacheable site assets between isolated account contexts."""

    analytics_hosts = {
        "www.googletagmanager.com", "static.ads-twitter.com", "analytics.twitter.com",
        "www.redditstatic.com", "t.co", "googleads.g.doubleclick.net",
        "stats.g.doubleclick.net", "static.cloudflareinsights.com",
    }

    def __init__(self, origin: str, enabled: bool = True, block_analytics: bool = True):
        self.host = urlsplit(origin).hostname
        self.enabled = enabled
        self.block_analytics = block_analytics
        self.blocked = 0
        self.entries: OrderedDict[tuple[str, str], Asset] = OrderedDict()
        self.locks: dict[tuple[str, str], asyncio.Lock] = {}
        self.size = 0
        self.hits = 0
        self.misses = 0
        self.served_bytes = 0
        self.capacity = 64 * 1024 * 1024

    def matches(self, url: str) -> bool:
        parsed = urlsplit(url)
        if self.block_analytics and parsed.hostname in self.analytics_hosts:
            return True
        if not self.enabled:
            return False
        if (parsed.scheme != "https" or parsed.hostname != self.host
                or parsed.port not in (None, 443) or parsed.username or parsed.password):
            return False
        if parsed.path.startswith(("/_next/static/", "/images/login/")):
            return True
        if parsed.path != "/_next/image":
            return False
        image = parse_qs(parsed.query).get("url", [""])[0]
        return image.startswith("/_next/static/media/") and ".." not in image

    async def install(self, context) -> None:
        if self.enabled or self.block_analytics:
            await context.route(self.matches, self.handle)

    async def handle(self, route) -> None:
        request = route.request
        if self.block_analytics and urlsplit(request.url).hostname in self.analytics_hosts:
            self.blocked += 1
            await route.abort()
            return
        if request.method != "GET":
            await route.continue_()
            return
        key = (request.url, request.headers.get("accept", ""))
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self.entries.get(key)
            if cached and cached.expires > time.monotonic():
                self.entries.move_to_end(key)
                self.hits += 1
                self.served_bytes += len(cached.body)
                await route.fulfill(status=200, headers=cached.headers, body=cached.body)
                return
            if cached:
                self.size -= len(self.entries.pop(key).body)
            self.misses += 1
            try:
                response = await route.fetch(max_redirects=0, timeout=30000)
            except BrowserError:
                await route.continue_()
                return
            try:
                headers = {name.lower(): value for name, value in response.headers.items()}
                control = headers.get("cache-control", "").lower()
                age = re.search(r"(?:^|,)\s*max-age=(\d+)", control)
                vary = {
                    item.strip().lower() for item in headers.get("vary", "").split(",")
                    if item.strip()
                }
                reusable = (
                    response.status == 200 and "public" in control
                    and age is not None and int(age.group(1)) > 0
                    and not any(item in control for item in ("private", "no-store", "no-cache"))
                    and "set-cookie" not in headers
                    and vary <= {"accept", "accept-encoding"}
                )
                if reusable:
                    body = await response.body()
                    if len(body) <= 8 * 1024 * 1024:
                        # route.fetch returns decoded bytes, so wire-compression headers must go.
                        omitted = {"content-encoding", "content-length", "transfer-encoding",
                                   "connection", "set-cookie"}
                        safe_headers = {name: value for name, value in headers.items()
                                        if name not in omitted}
                        while self.entries and self.size + len(body) > self.capacity:
                            _, removed = self.entries.popitem(last=False)
                            self.size -= len(removed.body)
                        self.entries[key] = Asset(
                            body, safe_headers, time.monotonic() + min(600, int(age.group(1)))
                        )
                        self.size += len(body)
                await route.fulfill(response=response)
            finally:
                await response.dispose()

    def stats(self) -> dict:
        return {"enabled": self.enabled, "analytics_blocked": self.blocked,
                "entries": len(self.entries), "memory_bytes": self.size,
                "hits": self.hits, "misses": self.misses, "served_decoded_bytes": self.served_bytes}

    def clear(self) -> None:
        self.entries.clear()
        self.locks.clear()
        self.size = 0
