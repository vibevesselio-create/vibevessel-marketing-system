"""
Shared helpers for music workflow scripts (SoundCloud sync, Notion integration).

Keeps rate limiting, backoff, and URL normalization in one place to reduce drift
across scripts and align with workspace standards.
"""

from __future__ import annotations

import logging
import random
import time
from collections import deque
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse

import requests


LOGGER = logging.getLogger(__name__)


def normalize_soundcloud_url(url: str) -> str:
    """Normalize a SoundCloud URL by removing query/fragment and trailing slash."""
    if not url:
        return ""
    candidate = url.strip()
    try:
        parsed = urlparse(candidate)
        if not parsed.scheme:
            return candidate
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            query="",
            fragment="",
            path=parsed.path.rstrip("/"),
        )
        return urlunparse(normalized)
    except Exception:
        return candidate


def resolve_property_name(prop_types: Dict[str, str], candidates: list[str]) -> Optional[str]:
    for name in candidates:
        if name in prop_types:
            return name
    return None


def build_text_filter(prop_name: str, prop_type: str, value: str) -> Optional[dict]:
    if not prop_name or not value:
        return None
    if prop_type == "title":
        return {"property": prop_name, "title": {"equals": value}}
    if prop_type == "rich_text":
        return {"property": prop_name, "rich_text": {"equals": value}}
    if prop_type == "url":
        return {"property": prop_name, "url": {"equals": value}}
    return None


class RateLimiter:
    """Simple sliding-window rate limiter."""

    def __init__(self, max_requests_per_minute: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max(1, int(max_requests_per_minute))
        self.window_seconds = max(1, int(window_seconds))
        self.timestamps: deque[float] = deque()

    def wait(self) -> None:
        now = time.time()
        while self.timestamps and now - self.timestamps[0] > self.window_seconds:
            self.timestamps.popleft()

        if len(self.timestamps) >= self.max_requests:
            oldest = self.timestamps[0]
            sleep_for = self.window_seconds - (now - oldest) + 0.05
            if sleep_for > 0:
                time.sleep(sleep_for)

        self.timestamps.append(time.time())


class NotionClient:
    """Minimal Notion API client with rate limiting and backoff."""

    def __init__(
        self,
        token: str,
        notion_version: str,
        max_retries: int = 5,
        rate_limit_per_minute: int = 60,
        timeout: int = 30,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.base = "https://api.notion.com/v1"
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.rate_limiter = RateLimiter(rate_limit_per_minute)
        self.logger = logger or LOGGER
        self.session = requests.Session()
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": notion_version,
            "Content-Type": "application/json",
        }

    def _backoff(self, attempt: int) -> float:
        base = min(20.0, 2 ** max(0, attempt))
        return base + random.random()

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> Any:
        url = path if path.startswith("http") else f"{self.base}{path}"
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            self.rate_limiter.wait()
            try:
                resp = self.session.request(
                    method,
                    url,
                    headers=self.headers,
                    json=body,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                sleep_for = self._backoff(attempt)
                self.logger.warning("Notion request error (%s). Retrying in %.1fs", exc, sleep_for)
                time.sleep(sleep_for)
                continue

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                sleep_for = float(retry_after) if retry_after else self._backoff(attempt)
                self.logger.warning("Notion rate limit hit. Retrying in %.1fs", sleep_for)
                time.sleep(sleep_for)
                continue

            if resp.status_code >= 500:
                if attempt >= self.max_retries:
                    break
                sleep_for = self._backoff(attempt)
                self.logger.warning("Notion server error %s. Retrying in %.1fs", resp.status_code, sleep_for)
                time.sleep(sleep_for)
                continue

            if resp.status_code >= 400:
                raise RuntimeError(f"Notion API error {resp.status_code}: {resp.text}")

            if resp.status_code == 204 or not resp.content:
                return None
            try:
                return resp.json()
            except ValueError:
                return resp.text

        raise RuntimeError(f"Notion API request failed after retries: {last_error}")

    def get_database(self, database_id: str) -> dict:
        return self._request("get", f"/databases/{database_id}")

    def query_database(self, database_id: str, query: dict) -> dict:
        return self._request("post", f"/databases/{database_id}/query", query)

    def create_page(self, database_id: str, properties: dict) -> dict:
        body = {"parent": {"database_id": database_id}, "properties": properties}
        return self._request("post", "/pages", body)

    def update_page(self, page_id: str, properties: dict) -> dict:
        body = {"properties": properties}
        return self._request("patch", f"/pages/{page_id}", body)

    def get_page(self, page_id: str) -> dict:
        """Retrieve a Notion page by ID."""
        return self._request("get", f"/pages/{page_id}")