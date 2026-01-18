"""
Adobe Lightroom API Client

Comprehensive Python client for Lightroom API operations including:
- Account and catalog management
- Asset listing and retrieval
- Album management
- Rendition access
- Upload operations

VERSION: 1.0.0
CREATED: 2026-01-18
AUTHOR: Claude Code Agent
"""

import os
import time
import logging
from dataclasses import dataclass, field
from typing import Iterator, Optional
from pathlib import Path
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


@dataclass
class Asset:
    """Lightroom asset representation."""
    id: str
    subtype: str  # 'image' or 'video'
    filename: str
    capture_date: Optional[str] = None
    import_timestamp: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    location: Optional[dict] = None
    camera: Optional[str] = None
    raw_data: dict = field(default_factory=dict)

    @classmethod
    def from_api_response(cls, data: dict) -> "Asset":
        """Create Asset from API response."""
        payload = data.get("payload", {})
        import_source = payload.get("importSource", {})
        develop = payload.get("develop", {})
        location = payload.get("location", {})
        exif = payload.get("exif", {})

        camera = None
        if exif.get("make") or exif.get("model"):
            camera = f"{exif.get('make', '')} {exif.get('model', '')}".strip()

        return cls(
            id=data.get("id", ""),
            subtype=payload.get("subtype", "image"),
            filename=import_source.get("fileName", ""),
            capture_date=payload.get("captureDate"),
            import_timestamp=import_source.get("importTimestamp"),
            width=develop.get("croppedWidth"),
            height=develop.get("croppedHeight"),
            location=location if location else None,
            camera=camera,
            raw_data=data,
        )


@dataclass
class Album:
    """Lightroom album representation."""
    id: str
    name: str
    subtype: str
    asset_count: int = 0
    created: Optional[str] = None
    updated: Optional[str] = None
    raw_data: dict = field(default_factory=dict)

    @classmethod
    def from_api_response(cls, data: dict) -> "Album":
        """Create Album from API response."""
        payload = data.get("payload", {})
        return cls(
            id=data.get("id", ""),
            name=payload.get("name", ""),
            subtype=payload.get("subtype", ""),
            asset_count=payload.get("assetCount", 0),
            created=data.get("created"),
            updated=data.get("updated"),
            raw_data=data,
        )


class LightroomClient:
    """
    Adobe Lightroom API client.

    Provides methods for interacting with Lightroom cloud storage:
    - Account and catalog operations
    - Asset management
    - Album management
    - Rendition retrieval

    Usage:
        client = LightroomClient(access_token="...", client_id="...")

        # Get catalog
        catalog = client.get_catalog()

        # List assets
        for asset in client.list_assets(catalog['id']):
            print(asset.filename)

        # Get rendition
        rendition_url = client.get_rendition_url(catalog['id'], asset.id, '1280')
    """

    API_BASE = "https://lr.adobe.io/v2"

    def __init__(
        self,
        access_token: Optional[str] = None,
        client_id: Optional[str] = None,
        refresh_callback: Optional[callable] = None,
    ):
        """
        Initialize Lightroom client.

        Args:
            access_token: OAuth access token (env: ADOBE_ACCESS_TOKEN)
            client_id: Adobe client ID (env: ADOBE_CLIENT_ID)
            refresh_callback: Optional callback for token refresh
        """
        self.access_token = access_token or os.environ.get("ADOBE_ACCESS_TOKEN")
        self.client_id = client_id or os.environ.get("ADOBE_CLIENT_ID")
        self.refresh_callback = refresh_callback

        if not self.access_token:
            raise ValueError("access_token is required (or set ADOBE_ACCESS_TOKEN env var)")
        if not self.client_id:
            raise ValueError("client_id is required (or set ADOBE_CLIENT_ID env var)")

        self._http_client = httpx.Client(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "X-API-Key": self.client_id,
                "Content-Type": "application/json",
            },
        )

    def __del__(self):
        """Cleanup HTTP client."""
        if hasattr(self, "_http_client"):
            self._http_client.close()

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        retry_on_401: bool = True,
    ) -> dict:
        """
        Make authenticated API request.

        Args:
            method: HTTP method
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json_data: JSON body for POST/PUT
            retry_on_401: Retry once with refreshed token on 401

        Returns:
            Parsed JSON response
        """
        url = f"{self.API_BASE}/{endpoint.lstrip('/')}"

        response = self._http_client.request(
            method,
            url,
            params=params,
            json=json_data,
        )

        # Handle rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            logger.warning(f"Rate limited, waiting {retry_after}s")
            time.sleep(retry_after)
            return self._request(method, endpoint, params, json_data, retry_on_401)

        # Handle authentication errors
        if response.status_code == 401 and retry_on_401 and self.refresh_callback:
            logger.info("Token expired, attempting refresh")
            new_token = self.refresh_callback()
            if new_token:
                self.access_token = new_token
                self._http_client.headers["Authorization"] = f"Bearer {new_token}"
                return self._request(method, endpoint, params, json_data, retry_on_401=False)

        response.raise_for_status()
        return response.json() if response.text else {}

    # ===== Account & Catalog Operations =====

    def get_account(self) -> dict:
        """
        Get Adobe account information.

        Returns:
            Account details including entitlements
        """
        return self._request("GET", "account")

    def get_catalog(self) -> dict:
        """
        Get user's Lightroom catalog.

        Returns:
            Catalog details including id and stats
        """
        return self._request("GET", "catalog")

    # ===== Asset Operations =====

    def list_assets(
        self,
        catalog_id: str,
        limit: int = 100,
        subtype: Optional[str] = None,
        captured_after: Optional[str] = None,
        captured_before: Optional[str] = None,
    ) -> Iterator[Asset]:
        """
        List assets in catalog with pagination.

        Args:
            catalog_id: Catalog ID
            limit: Results per page
            subtype: Filter by type ('image' or 'video')
            captured_after: Filter by capture date (ISO format)
            captured_before: Filter by capture date (ISO format)

        Yields:
            Asset objects
        """
        params = {"limit": limit}
        if subtype:
            params["subtype"] = subtype
        if captured_after:
            params["captured_after"] = captured_after
        if captured_before:
            params["captured_before"] = captured_before

        cursor = None
        page_count = 0
        max_pages = 1000  # Safety limit

        while page_count < max_pages:
            if cursor:
                params["start"] = cursor

            response = self._request("GET", f"catalogs/{catalog_id}/assets", params=params)

            for resource in response.get("resources", []):
                yield Asset.from_api_response(resource)

            # Check for next page
            links = response.get("links", {})
            if links.get("next"):
                cursor = links["next"].get("href", "").split("start=")[-1].split("&")[0]
                page_count += 1
                time.sleep(0.1)  # Rate limiting
            else:
                break

    def get_asset(self, catalog_id: str, asset_id: str) -> Asset:
        """
        Get single asset by ID.

        Args:
            catalog_id: Catalog ID
            asset_id: Asset ID

        Returns:
            Asset object
        """
        response = self._request("GET", f"catalogs/{catalog_id}/assets/{asset_id}")
        return Asset.from_api_response(response)

    def get_all_assets(
        self,
        catalog_id: str,
        max_assets: Optional[int] = None,
        **kwargs,
    ) -> list[Asset]:
        """
        Get all assets as a list.

        Args:
            catalog_id: Catalog ID
            max_assets: Maximum assets to retrieve
            **kwargs: Additional filter arguments

        Returns:
            List of Asset objects
        """
        assets = []
        for asset in self.list_assets(catalog_id, **kwargs):
            assets.append(asset)
            if max_assets and len(assets) >= max_assets:
                break
        return assets

    # ===== Album Operations =====

    def list_albums(
        self,
        catalog_id: str,
        limit: int = 100,
        subtype: Optional[str] = None,
    ) -> Iterator[Album]:
        """
        List albums in catalog.

        Args:
            catalog_id: Catalog ID
            limit: Results per page
            subtype: Filter by album type

        Yields:
            Album objects
        """
        params = {"limit": limit}
        if subtype:
            params["subtype"] = subtype

        cursor = None

        while True:
            if cursor:
                params["start"] = cursor

            response = self._request("GET", f"catalogs/{catalog_id}/albums", params=params)

            for resource in response.get("resources", []):
                yield Album.from_api_response(resource)

            links = response.get("links", {})
            if links.get("next"):
                cursor = links["next"].get("href", "").split("start=")[-1].split("&")[0]
                time.sleep(0.1)
            else:
                break

    def get_album(self, catalog_id: str, album_id: str) -> Album:
        """
        Get single album by ID.

        Args:
            catalog_id: Catalog ID
            album_id: Album ID

        Returns:
            Album object
        """
        response = self._request("GET", f"catalogs/{catalog_id}/albums/{album_id}")
        return Album.from_api_response(response)

    def list_album_assets(
        self,
        catalog_id: str,
        album_id: str,
        limit: int = 100,
    ) -> Iterator[Asset]:
        """
        List assets in an album.

        Args:
            catalog_id: Catalog ID
            album_id: Album ID
            limit: Results per page

        Yields:
            Asset objects
        """
        params = {"limit": limit}
        cursor = None

        while True:
            if cursor:
                params["start"] = cursor

            response = self._request(
                "GET",
                f"catalogs/{catalog_id}/albums/{album_id}/assets",
                params=params,
            )

            for resource in response.get("resources", []):
                yield Asset.from_api_response(resource)

            links = response.get("links", {})
            if links.get("next"):
                cursor = links["next"].get("href", "").split("start=")[-1].split("&")[0]
                time.sleep(0.1)
            else:
                break

    # ===== Rendition Operations =====

    def get_rendition_url(
        self,
        catalog_id: str,
        asset_id: str,
        size: str = "1280",
    ) -> str:
        """
        Get rendition URL for an asset.

        Args:
            catalog_id: Catalog ID
            asset_id: Asset ID
            size: Rendition size (thumbnail2x, 640, 1280, 2048, full)

        Returns:
            Rendition URL
        """
        response = self._request(
            "GET",
            f"catalogs/{catalog_id}/assets/{asset_id}/renditions/{size}",
        )
        return response.get("href", "")

    def download_rendition(
        self,
        catalog_id: str,
        asset_id: str,
        size: str = "1280",
        output_path: Optional[Path] = None,
    ) -> bytes:
        """
        Download rendition for an asset.

        Args:
            catalog_id: Catalog ID
            asset_id: Asset ID
            size: Rendition size
            output_path: Optional path to save file

        Returns:
            Rendition bytes
        """
        url = self.get_rendition_url(catalog_id, asset_id, size)
        if not url:
            raise ValueError("Could not get rendition URL")

        response = self._http_client.get(url)
        response.raise_for_status()

        content = response.content

        if output_path:
            output_path.write_bytes(content)
            logger.info(f"Saved rendition to {output_path}")

        return content

    # ===== Utility Methods =====

    def get_catalog_stats(self, catalog_id: str) -> dict:
        """
        Get catalog statistics.

        Args:
            catalog_id: Catalog ID

        Returns:
            Statistics dict
        """
        catalog = self.get_catalog()
        albums = list(self.list_albums(catalog_id))

        payload = catalog.get("payload", {})
        stats = payload.get("stats", {})

        return {
            "catalog_id": catalog_id,
            "total_images": stats.get("images", 0),
            "total_videos": stats.get("videos", 0),
            "total_albums": len(albums),
            "storage_used": stats.get("storageUsed", 0),
            "created": catalog.get("created"),
        }

    def search_by_filename(
        self,
        catalog_id: str,
        filename: str,
        max_results: int = 100,
    ) -> list[Asset]:
        """
        Search assets by filename.

        Args:
            catalog_id: Catalog ID
            filename: Filename to search (case-insensitive)
            max_results: Maximum results

        Returns:
            Matching assets
        """
        filename_lower = filename.lower()
        matches = []

        for asset in self.list_assets(catalog_id):
            if filename_lower in asset.filename.lower():
                matches.append(asset)
                if len(matches) >= max_results:
                    break

        return matches
