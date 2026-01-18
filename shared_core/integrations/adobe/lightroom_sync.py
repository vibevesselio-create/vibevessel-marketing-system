"""
Adobe Lightroom to Notion Sync Module

Synchronizes Lightroom assets to Notion database (Photos Library).
Follows established patterns from DriveSheetsSync and WorkspaceEventsSync.

VERSION: 1.0.0
CREATED: 2026-01-18
AUTHOR: Claude Code Agent

Features:
- Upsert operations (create or update based on Lightroom Asset ID)
- Loop-guard properties to prevent automation loops
- Incremental sync support
- Comprehensive logging and error handling
"""

import os
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

import httpx

from .lightroom_client import LightroomClient, Asset

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Sync operation result."""
    success: bool
    total: int = 0
    created: int = 0
    updated: int = 0
    errors: int = 0
    error_details: list = field(default_factory=list)
    duration_seconds: float = 0.0
    message: str = ""


class LightroomNotionSync:
    """
    Syncs Lightroom assets to Notion database.

    This class handles:
    - Discovering the target Notion database
    - Mapping Lightroom assets to Notion properties
    - Upserting pages (create or update)
    - Loop-guard property management
    - Execution logging

    Usage:
        sync = LightroomNotionSync(
            lightroom_client=LightroomClient(...),
            notion_token="your_notion_token",
            database_name="Photos Library"
        )

        result = sync.sync_assets(catalog_id)
        print(f"Synced {result.created} new, {result.updated} updated")
    """

    NOTION_API_BASE = "https://api.notion.com/v1"
    NOTION_VERSION = "2025-09-03"

    # Loop-guard properties to prevent automation loops
    AUTOMATION_SOURCE_PROP = "Seren-Automation-Source"
    AUTOMATION_EVENT_ID_PROP = "Seren-Automation-Event-ID"
    AUTOMATION_NODE_ID_PROP = "Seren-Automation-Node-ID"
    AUTOMATION_SOURCE_VALUE = "Python-Lightroom-Sync"
    NODE_ID = "lightroom-sync-v1"

    def __init__(
        self,
        lightroom_client: LightroomClient,
        notion_token: Optional[str] = None,
        database_name: str = "Photos Library",
        database_id: Optional[str] = None,
    ):
        """
        Initialize sync handler.

        Args:
            lightroom_client: Configured LightroomClient instance
            notion_token: Notion API token (env: NOTION_TOKEN)
            database_name: Target database name
            database_id: Target database ID (skips discovery)
        """
        self.lr_client = lightroom_client
        self.notion_token = notion_token or os.environ.get("NOTION_TOKEN")
        self.database_name = database_name
        self._database_id = database_id

        if not self.notion_token:
            raise ValueError("notion_token is required (or set NOTION_TOKEN env var)")

        self._http_client = httpx.Client(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self.notion_token}",
                "Notion-Version": self.NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )

        # Cache for database discovery
        self._db_cache: dict[str, str] = {}

    def __del__(self):
        """Cleanup HTTP client."""
        if hasattr(self, "_http_client"):
            self._http_client.close()

    def _notion_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None,
    ) -> dict:
        """Make Notion API request."""
        url = f"{self.NOTION_API_BASE}/{endpoint.lstrip('/')}"

        response = self._http_client.request(
            method,
            url,
            json=json_data,
        )

        if response.status_code >= 200 and response.status_code < 300:
            return response.json() if response.text else {}

        raise Exception(f"Notion API error {response.status_code}: {response.text}")

    def _discover_database(self, name: str) -> Optional[str]:
        """
        Discover database ID by name.

        Args:
            name: Database name to search for

        Returns:
            Database ID or None
        """
        if name in self._db_cache:
            return self._db_cache[name]

        cursor = None
        for _ in range(10):  # Max 10 pages
            body = {
                "query": name,
                "page_size": 100,
                "filter": {"property": "object", "value": "data_source"},
            }
            if cursor:
                body["start_cursor"] = cursor

            response = self._notion_request("POST", "search", body)

            for result in response.get("results", []):
                title = ""
                if result.get("title"):
                    title = result["title"][0].get("plain_text", "")
                elif result.get("name"):
                    title = result["name"]

                if title.lower() == name.lower():
                    db_id = result.get("id", "").replace("-", "")
                    if db_id:
                        self._db_cache[name] = db_id
                        logger.info(f"Discovered database '{name}': {db_id}")
                        return db_id

            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")

        logger.warning(f"Could not find database: {name}")
        return None

    @property
    def database_id(self) -> Optional[str]:
        """Get target database ID."""
        if self._database_id:
            return self._database_id
        return self._discover_database(self.database_name)

    def _ensure_loop_guard_properties(self, database_id: str) -> bool:
        """Ensure loop-guard properties exist on database."""
        try:
            db = self._notion_request("GET", f"databases/{database_id}")
            props = db.get("properties", {})
            to_add = {}

            if self.AUTOMATION_SOURCE_PROP not in props:
                to_add[self.AUTOMATION_SOURCE_PROP] = {"rich_text": {}}
            if self.AUTOMATION_EVENT_ID_PROP not in props:
                to_add[self.AUTOMATION_EVENT_ID_PROP] = {"rich_text": {}}
            if self.AUTOMATION_NODE_ID_PROP not in props:
                to_add[self.AUTOMATION_NODE_ID_PROP] = {"rich_text": {}}

            if to_add:
                self._notion_request("PATCH", f"databases/{database_id}", {"properties": to_add})
                logger.info(f"Added loop-guard properties to database")

            return True
        except Exception as e:
            logger.warning(f"Could not ensure loop-guard properties: {e}")
            return False

    def _find_page_by_asset_id(self, database_id: str, asset_id: str) -> Optional[str]:
        """Find existing page by Lightroom Asset ID."""
        try:
            query = {
                "filter": {
                    "property": "Lightroom-Asset-ID",
                    "rich_text": {"equals": asset_id},
                },
                "page_size": 1,
            }
            response = self._notion_request("POST", f"databases/{database_id}/query", query)
            results = response.get("results", [])
            if results:
                return results[0].get("id")
        except Exception as e:
            logger.warning(f"Could not find page by asset ID: {e}")
        return None

    def _map_asset_to_properties(self, asset: Asset, include_loop_guard: bool = True) -> dict:
        """
        Map Lightroom asset to Notion properties.

        Args:
            asset: Lightroom Asset object
            include_loop_guard: Include loop-guard properties

        Returns:
            Notion properties dict
        """
        properties = {
            "Name": {
                "title": [{"text": {"content": asset.filename or asset.id or "Untitled"}}]
            },
            "Lightroom-Asset-ID": {
                "rich_text": [{"text": {"content": asset.id}}]
            },
            "File Type": {
                "rich_text": [{"text": {"content": asset.subtype or ""}}]
            },
            "Original Filename": {
                "rich_text": [{"text": {"content": asset.filename or ""}}]
            },
        }

        # Add optional properties
        if asset.import_timestamp:
            properties["Import Date"] = {
                "rich_text": [{"text": {"content": asset.import_timestamp}}]
            }

        if asset.capture_date:
            try:
                # Parse and format date
                date_str = asset.capture_date.split("T")[0]
                properties["Capture Date"] = {"date": {"start": date_str}}
            except Exception:
                pass

        if asset.width and asset.height:
            properties["Width"] = {"number": asset.width}
            properties["Height"] = {"number": asset.height}

        if asset.location:
            lat = asset.location.get("latitude")
            lon = asset.location.get("longitude")
            if lat and lon:
                properties["Location"] = {
                    "rich_text": [{"text": {"content": f"{lat}, {lon}"}}]
                }

        if asset.camera:
            properties["Camera"] = {
                "rich_text": [{"text": {"content": asset.camera}}]
            }

        # Add loop-guard properties
        if include_loop_guard:
            properties[self.AUTOMATION_SOURCE_PROP] = {
                "rich_text": [{"text": {"content": self.AUTOMATION_SOURCE_VALUE}}]
            }
            properties[self.AUTOMATION_NODE_ID_PROP] = {
                "rich_text": [{"text": {"content": self.NODE_ID}}]
            }
            properties[self.AUTOMATION_EVENT_ID_PROP] = {
                "rich_text": [{"text": {"content": asset.id}}]
            }

        return properties

    def upsert_asset(self, asset: Asset) -> dict:
        """
        Upsert a single asset to Notion.

        Args:
            asset: Lightroom Asset object

        Returns:
            Result dict with ok, pageId, action
        """
        db_id = self.database_id
        if not db_id:
            return {"ok": False, "error": f"Database not found: {self.database_name}"}

        # Ensure loop-guard properties exist
        can_tag = self._ensure_loop_guard_properties(db_id)

        # Find existing page
        page_id = self._find_page_by_asset_id(db_id, asset.id)

        # Map asset to properties
        properties = self._map_asset_to_properties(asset, include_loop_guard=can_tag)

        try:
            if page_id:
                # Update existing page
                self._notion_request("PATCH", f"pages/{page_id}", {"properties": properties})
                return {"ok": True, "pageId": page_id, "action": "updated"}
            else:
                # Create new page
                result = self._notion_request("POST", "pages", {
                    "parent": {"database_id": db_id},
                    "properties": properties,
                })
                return {"ok": True, "pageId": result.get("id"), "action": "created"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def sync_assets(
        self,
        catalog_id: Optional[str] = None,
        limit: Optional[int] = None,
        dry_run: bool = False,
    ) -> SyncResult:
        """
        Sync all assets from Lightroom catalog to Notion.

        Args:
            catalog_id: Catalog ID (auto-discovered if not provided)
            limit: Maximum assets to sync
            dry_run: If True, don't actually sync

        Returns:
            SyncResult with statistics
        """
        start_time = time.time()

        # Get catalog if not provided
        if not catalog_id:
            try:
                catalog = self.lr_client.get_catalog()
                catalog_id = catalog.get("id")
            except Exception as e:
                return SyncResult(
                    success=False,
                    message=f"Could not get catalog: {e}",
                )

        if not catalog_id:
            return SyncResult(success=False, message="No catalog ID available")

        # Get database ID
        db_id = self.database_id
        if not db_id:
            return SyncResult(
                success=False,
                message=f"Could not find database: {self.database_name}",
            )

        logger.info(f"Starting sync to database {db_id}")

        # Get assets
        try:
            if limit:
                assets = self.lr_client.get_all_assets(catalog_id, max_assets=limit)
            else:
                assets = self.lr_client.get_all_assets(catalog_id)
        except Exception as e:
            return SyncResult(success=False, message=f"Could not list assets: {e}")

        result = SyncResult(
            success=True,
            total=len(assets),
        )

        if dry_run:
            result.message = f"[DRY RUN] Would sync {len(assets)} assets"
            logger.info(result.message)
            return result

        # Process each asset
        for i, asset in enumerate(assets):
            try:
                upsert_result = self.upsert_asset(asset)

                if upsert_result.get("ok"):
                    if upsert_result.get("action") == "created":
                        result.created += 1
                    elif upsert_result.get("action") == "updated":
                        result.updated += 1
                else:
                    result.errors += 1
                    result.error_details.append({
                        "asset_id": asset.id,
                        "error": upsert_result.get("error"),
                    })

            except Exception as e:
                result.errors += 1
                result.error_details.append({
                    "asset_id": asset.id,
                    "error": str(e),
                })

            # Rate limiting
            if (i + 1) % 10 == 0:
                time.sleep(0.5)
                logger.info(f"Processed {i + 1}/{len(assets)} assets")

        result.duration_seconds = time.time() - start_time
        result.message = (
            f"Sync complete: {result.created} created, "
            f"{result.updated} updated, {result.errors} errors "
            f"in {result.duration_seconds:.1f}s"
        )
        logger.info(result.message)

        return result

    def create_execution_log(self, sync_result: SyncResult) -> Optional[str]:
        """
        Create execution log in Notion.

        Args:
            sync_result: Sync operation result

        Returns:
            Created page ID or None
        """
        try:
            exec_db_id = self._discover_database("Execution-Logs")
            if not exec_db_id:
                return None

            self._ensure_loop_guard_properties(exec_db_id)

            properties = {
                "Script Name": {"title": [{"text": {"content": "Python Lightroom Sync"}}]},
                "Execution Result": {
                    "rich_text": [{
                        "text": {"content": sync_result.message[:2000]}  # Truncate if needed
                    }]
                },
                "Last Run": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
                self.AUTOMATION_SOURCE_PROP: {
                    "rich_text": [{"text": {"content": self.AUTOMATION_SOURCE_VALUE}}]
                },
                self.AUTOMATION_NODE_ID_PROP: {
                    "rich_text": [{"text": {"content": self.NODE_ID}}]
                },
            }

            result = self._notion_request("POST", "pages", {
                "parent": {"database_id": exec_db_id},
                "properties": properties,
            })

            return result.get("id")
        except Exception as e:
            logger.warning(f"Could not create execution log: {e}")
            return None
