"""
Eagle API client for music workflow.

This module provides integration with Eagle library for importing
and managing audio files as assets.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any
import urllib.request
import urllib.error
import urllib.parse

from music_workflow.utils.errors import EagleIntegrationError
from music_workflow.config.settings import get_settings


@dataclass
class EagleItem:
    """Represents an item in Eagle library."""
    id: str
    name: str
    ext: str
    tags: List[str]
    url: Optional[str] = None
    annotation: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    folders: List[str] = None
    mtime: Optional[int] = None
    path: Optional[str] = None

    def __post_init__(self):
        if self.folders is None:
            self.folders = []


class EagleClient:
    """Client for Eagle local API.

    Eagle exposes a local HTTP API on port 41595 for library management.
    This client provides methods for importing files, searching, and
    managing tags and folders.
    """

    DEFAULT_PORT = 41595
    BASE_URL = "http://localhost"

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        library_path: Optional[Path] = None,
    ):
        """Initialize the Eagle client.

        Args:
            port: Eagle API port (default 41595)
            library_path: Optional path to Eagle library
        """
        self.port = port
        self.base_url = f"{self.BASE_URL}:{port}"
        settings = get_settings()
        self.library_path = library_path or settings.eagle.library_path

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict] = None,
    ) -> Dict:
        """Make a request to the Eagle API.

        Args:
            endpoint: API endpoint
            method: HTTP method
            data: Request data for POST, or query parameters for GET

        Returns:
            Response data
        """
        url = f"{self.base_url}/api/{endpoint}"

        try:
            if method == "POST" and data:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(data).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            elif method == "GET" and data:
                # Add query parameters for GET requests
                query_string = urllib.parse.urlencode(data)
                url = f"{url}?{query_string}"
                req = urllib.request.Request(url, method=method)
            else:
                req = urllib.request.Request(url, method=method)

            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))

        except urllib.error.URLError as e:
            raise EagleIntegrationError(
                f"Eagle API not available: {e}",
                library_path=str(self.library_path),
                details={"endpoint": endpoint, "error": str(e)}
            )
        except json.JSONDecodeError as e:
            raise EagleIntegrationError(
                f"Invalid Eagle API response: {e}",
                details={"endpoint": endpoint, "error": str(e)}
            )

    def is_available(self) -> bool:
        """Check if Eagle API is available.

        Returns:
            True if Eagle is running and accessible
        """
        try:
            self._request("application/info")
            return True
        except EagleIntegrationError:
            return False

    def get_library_info(self) -> Dict:
        """Get information about the current library.

        Returns:
            Library information
        """
        response = self._request("library/info")
        return response.get("data", {})

    def import_file(
        self,
        file_path: Path,
        name: Optional[str] = None,
        website: Optional[str] = None,
        tags: Optional[List[str]] = None,
        annotation: Optional[str] = None,
        folder_id: Optional[str] = None,
        fingerprint: Optional[str] = None,
        auto_sync_fingerprint: bool = True,
    ) -> str:
        """Import a file to Eagle library.

        Args:
            file_path: Path to file to import
            name: Display name (defaults to filename)
            website: Source URL
            tags: List of tags
            annotation: Annotation text
            folder_id: Target folder ID
            fingerprint: Optional fingerprint hash to add as tag
            auto_sync_fingerprint: If True and fingerprint not provided,
                try to extract from file metadata

        Returns:
            Created item ID

        Raises:
            EagleIntegrationError: If import fails
        """
        if not file_path.exists():
            raise EagleIntegrationError(
                f"File not found: {file_path}",
                details={"file_path": str(file_path)}
            )

        # Try to extract fingerprint from file metadata if not provided
        if not fingerprint and auto_sync_fingerprint:
            try:
                # Import fingerprint extraction function
                import sys
                from pathlib import Path as PathLib
                project_root = PathLib(__file__).resolve().parent.parent.parent.parent
                if str(project_root) not in sys.path:
                    sys.path.insert(0, str(project_root))
                
                try:
                    from scripts.music_library_remediation import extract_fingerprint_from_metadata
                    extracted_fp = extract_fingerprint_from_metadata(str(file_path))
                    if extracted_fp:
                        fingerprint = extracted_fp
                except ImportError:
                    pass  # Fingerprint extraction not available
            except Exception:
                pass  # Silently fail if fingerprint extraction fails

        # Add fingerprint tag if available
        final_tags = list(tags) if tags else []
        if fingerprint:
            fp_tag = f"fingerprint:{fingerprint.lower()}"
            if fp_tag not in final_tags:
                final_tags.append(fp_tag)

        data = {
            "path": str(file_path.absolute()),
            "name": name or file_path.stem,
        }

        if website:
            data["website"] = website
        if final_tags:
            data["tags"] = final_tags
        if annotation:
            data["annotation"] = annotation
        if folder_id:
            data["folderId"] = folder_id

        response = self._request("item/addFromPath", method="POST", data=data)

        if response.get("status") != "success":
            raise EagleIntegrationError(
                f"Import failed: {response.get('message', 'Unknown error')}",
                details={"file_path": str(file_path), "response": response}
            )

        return response.get("data", {}).get("id", "")

    def import_url(
        self,
        url: str,
        name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        annotation: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> str:
        """Import from a URL.

        Args:
            url: URL to import from
            name: Display name
            tags: List of tags
            annotation: Annotation text
            folder_id: Target folder ID

        Returns:
            Created item ID
        """
        data = {"url": url}

        if name:
            data["name"] = name
        if tags:
            data["tags"] = tags
        if annotation:
            data["annotation"] = annotation
        if folder_id:
            data["folderId"] = folder_id

        response = self._request("item/addFromURL", method="POST", data=data)

        if response.get("status") != "success":
            raise EagleIntegrationError(
                f"URL import failed: {response.get('message', 'Unknown error')}",
                details={"url": url, "response": response}
            )

        return response.get("data", {}).get("id", "")

    def search(
        self,
        keyword: Optional[str] = None,
        tags: Optional[List[str]] = None,
        folder_id: Optional[str] = None,
        ext: Optional[str] = None,
        limit: Optional[int] = 10000,
    ) -> List[EagleItem]:
        """Search Eagle library.

        Args:
            keyword: Search keyword
            tags: Filter by tags
            folder_id: Filter by folder
            ext: Filter by extension
            limit: Maximum results (default: 10000 to get all items)

        Returns:
            List of matching items
        """
        # Eagle search is done via item/list endpoint with filters
        # Note: Eagle API requires GET with query parameters, not POST
        params = {}
        if limit is not None:
            params["limit"] = limit

        if keyword:
            params["keyword"] = keyword
        if tags:
            # Tags need to be passed as a list in query string
            # Eagle API expects tags as comma-separated or multiple query params
            if isinstance(tags, list):
                params["tags"] = ",".join(tags)
            else:
                params["tags"] = tags
        if folder_id:
            params["folderId"] = folder_id
        if ext:
            params["ext"] = ext

        response = self._request("item/list", method="GET", data=params if params else None)

        items = []
        for item_data in response.get("data", []):
            items.append(EagleItem(
                id=item_data.get("id", ""),
                name=item_data.get("name", ""),
                ext=item_data.get("ext", ""),
                tags=item_data.get("tags", []),
                url=item_data.get("url"),
                annotation=item_data.get("annotation"),
                width=item_data.get("width"),
                height=item_data.get("height"),
                folders=item_data.get("folders", []),
                mtime=item_data.get("mtime"),
                path=item_data.get("path"),
            ))

        return items

    def get_item(self, item_id: str) -> Optional[EagleItem]:
        """Get an item by ID.

        Args:
            item_id: Item ID

        Returns:
            EagleItem or None if not found
        """
        try:
            # Eagle API requires GET with query parameter, not POST
            response = self._request("item/info", method="GET", data={"id": item_id})
            item_data = response.get("data", {})

            if not item_data:
                return None

            return EagleItem(
                id=item_data.get("id", ""),
                name=item_data.get("name", ""),
                ext=item_data.get("ext", ""),
                tags=item_data.get("tags", []),
                url=item_data.get("url"),
                annotation=item_data.get("annotation"),
                folders=item_data.get("folders", []),
                path=item_data.get("path"),  # Note: API doesn't return path, will be None
            )
        except EagleIntegrationError:
            return None

    def add_tags(self, item_id: str, tags: List[str]) -> bool:
        """Add tags to an item.

        Args:
            item_id: Item ID
            tags: Tags to add

        Returns:
            True if successful
        """
        # Get current item
        item = self.get_item(item_id)
        if not item:
            return False

        # Merge tags
        all_tags = list(set(item.tags + tags))

        response = self._request(
            "item/update",
            method="POST",
            data={"id": item_id, "tags": all_tags}
        )

        return response.get("status") == "success"

    def sync_fingerprint_tag(
        self,
        item_id: str,
        fingerprint: str,
        force: bool = False
    ) -> bool:
        """Sync fingerprint tag to an Eagle item.

        Args:
            item_id: Item ID
            fingerprint: Fingerprint hash string
            force: If True, replace existing fingerprint tag

        Returns:
            True if successfully synced
        """
        item = self.get_item(item_id)
        if not item:
            return False

        fp_tag = f"fingerprint:{fingerprint.lower()}"

        # Check if fingerprint tag already exists
        existing_fp_tags = [
            tag for tag in item.tags
            if tag.lower().startswith("fingerprint:")
        ]

        if existing_fp_tags and not force:
            # Fingerprint tag already exists
            return True

        # Remove old fingerprint tags if forcing update
        if force and existing_fp_tags:
            all_tags = [tag for tag in item.tags if tag not in existing_fp_tags]
        else:
            all_tags = list(item.tags)

        # Add new fingerprint tag
        if fp_tag not in all_tags:
            all_tags.append(fp_tag)

        response = self._request(
            "item/update",
            method="POST",
            data={"id": item_id, "tags": all_tags}
        )

        return response.get("status") == "success"

    def get_fingerprint(self, item_id: str) -> Optional[str]:
        """Extract fingerprint from an Eagle item's tags.

        Args:
            item_id: Item ID

        Returns:
            Fingerprint string if found, None otherwise
        """
        item = self.get_item(item_id)
        if not item:
            return None

        for tag in item.tags:
            if tag.lower().startswith("fingerprint:"):
                return tag.lower().replace("fingerprint:", "").strip()

        return None

    def search_by_fingerprint(self, fingerprint: str) -> List[EagleItem]:
        """Search for items by fingerprint tag.

        Args:
            fingerprint: Fingerprint hash string

        Returns:
            List of matching Eagle items
        """
        fp_tag = f"fingerprint:{fingerprint.lower()}"
        return self.search(tags=[fp_tag])

    def get_folders(self) -> List[Dict]:
        """Get all folders in the library.

        Returns:
            List of folder objects
        """
        response = self._request("folder/list")
        return response.get("data", [])

    def create_folder(
        self,
        name: str,
        parent_id: Optional[str] = None,
    ) -> str:
        """Create a new folder.

        Args:
            name: Folder name
            parent_id: Parent folder ID

        Returns:
            Created folder ID
        """
        data = {"folderName": name}
        if parent_id:
            data["parent"] = parent_id

        response = self._request("folder/create", method="POST", data=data)

        if response.get("status") != "success":
            raise EagleIntegrationError(
                f"Folder creation failed: {response.get('message', 'Unknown error')}",
                details={"name": name, "response": response}
            )

        return response.get("data", {}).get("id", "")


# Singleton instance
_eagle_client: Optional[EagleClient] = None


def get_eagle_client() -> EagleClient:
    """Get the global Eagle client instance."""
    global _eagle_client
    if _eagle_client is None:
        _eagle_client = EagleClient()
    return _eagle_client
