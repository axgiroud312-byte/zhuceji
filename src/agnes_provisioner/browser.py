from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright

from .config import Settings
from .public_cache import PublicAssetCache


class BrowserManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.playwright = None
        self.browser = None
        self.lock = asyncio.Lock()
        self.public_cache = PublicAssetCache(
            settings.base_url, settings.cache_public_assets, settings.block_analytics
        )

    async def start(self) -> None:
        async with self.lock:
            if self.browser:
                return
            self.playwright = await async_playwright().start()
            options = {"headless": self.settings.headless}
            if self.settings.browser_channel and self.settings.browser_channel != "chromium":
                options["channel"] = self.settings.browser_channel
            self.browser = await self.playwright.chromium.launch(**options)

    @asynccontextmanager
    async def page(self, proxy: dict | None = None, state: dict | None = None):
        await self.start()
        options = {"locale": "zh-CN", "accept_downloads": False}
        if proxy:
            options["proxy"] = proxy
        if state:
            options["storage_state"] = state
        context = await self.browser.new_context(**options)
        context.set_default_timeout(self.settings.browser_timeout_ms)
        try:
            await self.public_cache.install(context)
            page = await context.new_page()
            yield page
        finally:
            await context.close()

    async def close(self):
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        self.public_cache.clear()
