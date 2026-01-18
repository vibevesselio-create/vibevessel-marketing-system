"""
Notion API client wrapper for music workflow.

This module provides a Notion client wrapper specifically for music workflow
operations, building on the shared_core.notion utilities.
"""

from typing import Dict, List, Optional, Any
from notion_client import Client

from music_workflow.utils.errors import NotionIntegrationError
from music_workflow.config.settings import get_settings


class NotionClient:
    """Wrapper around Notion API for music workflow operations.

    Provides high-level methods for querying and updating Notion databases
    used by the music workflow system.
    """

    def __init__(self, auth_token: Optional[str] = None):
        """Initialize the Notion client.

        Args:
            auth_token: Notion API token. If not provided, uses shared_core
        """
        self._client = None
        self._auth_token = auth_token
        self._settings = get_settings()

    def _get_client(self) -> Client:
        """Get or create the Notion client (lazy loading)."""
        if self._client is None:
            if self._auth_token:
                self._client = Client(auth=self._auth_token)
            else:
                try:
                    from shared_core.notion import get_notion_client
                    self._client = get_notion_client()
                except ImportError:
                    import os
                    token = os.environ.get("NOTION_TOKEN")
                    if not token:
                        raise NotionIntegrationError(
                            "No Notion token available",
                            details={"hint": "Set NOTION_TOKEN environment variable"}
                        )
                    self._client = Client(auth=token)
        return self._client

    def query_database(
        self,
        database_id: str,
        filter: Optional[Dict] = None,
        sorts: Optional[List[Dict]] = None,
        page_size: int = 100,
    ) -> List[Dict]:
        """Query a Notion database.

        Args:
            database_id: The database ID to query
            filter: Optional filter dictionary
            sorts: Optional sort specifications
            page_size: Number of results per page

        Returns:
            List of page objects

        Raises:
            NotionIntegrationError: If query fails
        """
        client = self._get_client()

        try:
            query_params = {"database_id": database_id, "page_size": page_size}
            if filter:
                query_params["filter"] = filter
            if sorts:
                query_params["sorts"] = sorts

            results = []
            has_more = True
            start_cursor = None

            while has_more:
                if start_cursor:
                    query_params["start_cursor"] = start_cursor

                response = client.databases.query(**query_params)
                results.extend(response.get("results", []))
                has_more = response.get("has_more", False)
                start_cursor = response.get("next_cursor")

            return results

        except Exception as e:
            raise NotionIntegrationError(
                f"Database query failed: {e}",
                database_id=database_id,
                status_code=getattr(e, 'status', None),
                details={"error": str(e)}
            )

    def get_page(self, page_id: str) -> Dict:
        """Get a Notion page by ID.

        Args:
            page_id: The page ID to retrieve

        Returns:
            Page object

        Raises:
            NotionIntegrationError: If retrieval fails
        """
        client = self._get_client()

        try:
            return client.pages.retrieve(page_id=page_id)
        except Exception as e:
            raise NotionIntegrationError(
                f"Page retrieval failed: {e}",
                page_id=page_id,
                status_code=getattr(e, 'status', None),
                details={"error": str(e)}
            )

    def update_page(self, page_id: str, properties: Dict) -> Dict:
        """Update a Notion page.

        Args:
            page_id: The page ID to update
            properties: Properties to update

        Returns:
            Updated page object

        Raises:
            NotionIntegrationError: If update fails
        """
        client = self._get_client()

        try:
            return client.pages.update(page_id=page_id, properties=properties)
        except Exception as e:
            raise NotionIntegrationError(
                f"Page update failed: {e}",
                page_id=page_id,
                status_code=getattr(e, 'status', None),
                details={"error": str(e), "properties": list(properties.keys())}
            )

    def create_page(
        self,
        database_id: str,
        properties: Dict,
        children: Optional[List[Dict]] = None,
    ) -> Dict:
        """Create a new page in a database.

        Args:
            database_id: The database to create the page in
            properties: Page properties
            children: Optional page content blocks

        Returns:
            Created page object

        Raises:
            NotionIntegrationError: If creation fails
        """
        client = self._get_client()

        try:
            create_params = {
                "parent": {"database_id": database_id},
                "properties": properties,
            }
            if children:
                create_params["children"] = children

            return client.pages.create(**create_params)
        except Exception as e:
            raise NotionIntegrationError(
                f"Page creation failed: {e}",
                database_id=database_id,
                status_code=getattr(e, 'status', None),
                details={"error": str(e)}
            )

    def archive_page(self, page_id: str) -> Dict:
        """Archive (soft delete) a Notion page.

        Args:
            page_id: The page ID to archive

        Returns:
            Archived page object
        """
        return self.update_page(page_id, {"archived": True})


# Singleton instance
_notion_client: Optional[NotionClient] = None


def get_notion_client() -> NotionClient:
    """Get the global Notion client instance."""
    global _notion_client
    if _notion_client is None:
        _notion_client = NotionClient()
    return _notion_client
