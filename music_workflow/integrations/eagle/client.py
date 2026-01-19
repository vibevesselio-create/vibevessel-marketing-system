"""
Eagle API client for music workflow.

This module provides integration with Eagle library for importing
and managing audio files as assets. Includes file verification
to ensure all items have valid, non-corrupt files.

Version: 2026-01-18 - Added file verification support
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import urllib.request
import urllib.error
import urllib.parse

from music_workflow.utils.errors import EagleIntegrationError
from music_workflow.config.settings import get_settings

# Import file verification (with graceful fallback)
try:
    from sync_framework.core.file_verification import (
        EagleFileVerifier,
        FileVerificationResult,
        FileStatus,
        get_eagle_file_verifier,
    )
    FILE_VERIFICATION_AVAILABLE = True
except ImportError:
    FILE_VERIFICATION_AVAILABLE = False


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
    # File verification fields
    file_verified: bool = False
    file_exists: bool = False
    file_valid: bool = False

    def __post_init__(self):
        if self.folders is None:
            self.folders = []


class EagleClient:
    """Client for Eagle local API.

    Eagle exposes a local HTTP API on port 41595 for library management.
    This client provides methods for importing files, searching, and
    managing tags and folders.

    Includes automatic file verification to ensure items have valid files.
    """

    DEFAULT_PORT = 41595
    BASE_URL = "http://localhost"

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        library_path: Optional[Path] = None,
        verify_files: bool = True,
    ):
        """Initialize the Eagle client.

        Args:
            port: Eagle API port (default 41595)
            library_path: Optional path to Eagle library
            verify_files: Whether to verify file existence by default
        """
        self.port = port
        self.base_url = f"{self.BASE_URL}:{port}"
        settings = get_settings()
        self.library_path = library_path or settings.eagle.library_path
        self.verify_files = verify_files
        self._file_verifier: Optional[Any] = None

    @property
    def file_verifier(self):
        """Get file verifier instance (lazy initialization)."""
        if self._file_verifier is None and FILE_VERIFICATION_AVAILABLE:
            self._file_verifier = get_eagle_file_verifier(self.library_path)
        return self._file_verifier

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
        verify: Optional[bool] = None,
        skip_missing: bool = False,
    ) -> List[EagleItem]:
        """Search Eagle library with optional file verification.

        Args:
            keyword: Search keyword
            tags: Filter by tags
            folder_id: Filter by folder
            ext: Filter by extension
            limit: Maximum results (default: 10000 to get all items)
            verify: Whether to verify files (default: use instance setting)
            skip_missing: Whether to skip items with missing files

        Returns:
            List of matching items with file verification status
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

        # Determine whether to verify
        do_verify = verify if verify is not None else self.verify_files

        items = []
        for item_data in response.get("data", []):
            item_id = item_data.get("id", "")
            item_ext = item_data.get("ext", "")
            item_name = item_data.get("name", "")

            # Resolve and verify file path
            file_path = item_data.get("path")
            file_verified = False
            file_exists = False
            file_valid = False

            if do_verify and self.file_verifier:
                # Resolve path if not provided by API
                if not file_path:
                    resolved = self.file_verifier.resolve_eagle_path(
                        item_id, item_ext, item_name
                    )
                    if resolved:
                        file_path = str(resolved)

                # Verify file
                if file_path:
                    result = self.file_verifier.verify_file(Path(file_path))
                    file_verified = True
                    file_exists = result.status != FileStatus.MISSING
                    file_valid = result.is_valid

                    # Skip missing files if requested
                    if skip_missing and not file_exists:
                        continue

            items.append(EagleItem(
                id=item_id,
                name=item_name,
                ext=item_ext,
                tags=item_data.get("tags", []),
                url=item_data.get("url"),
                annotation=item_data.get("annotation"),
                width=item_data.get("width"),
                height=item_data.get("height"),
                folders=item_data.get("folders", []),
                mtime=item_data.get("mtime"),
                path=file_path,
                file_verified=file_verified,
                file_exists=file_exists,
                file_valid=file_valid,
            ))

        return items

    def get_item(self, item_id: str, verify: Optional[bool] = None) -> Optional[EagleItem]:
        """Get an item by ID with optional file verification.

        Args:
            item_id: Item ID
            verify: Whether to verify file (default: use instance setting)

        Returns:
            EagleItem with file verification status, or None if not found
        """
        try:
            # Eagle API requires GET with query parameter, not POST
            response = self._request("item/info", method="GET", data={"id": item_id})
            item_data = response.get("data", {})

            if not item_data:
                return None

            item_ext = item_data.get("ext", "")
            item_name = item_data.get("name", "")

            # Resolve and verify file path
            file_path = item_data.get("path")  # Note: API doesn't return path
            file_verified = False
            file_exists = False
            file_valid = False

            do_verify = verify if verify is not None else self.verify_files

            if do_verify and self.file_verifier:
                # Resolve path from library structure
                if not file_path:
                    resolved = self.file_verifier.resolve_eagle_path(
                        item_id, item_ext, item_name
                    )
                    if resolved:
                        file_path = str(resolved)

                # Verify file
                if file_path:
                    result = self.file_verifier.verify_file(Path(file_path))
                    file_verified = True
                    file_exists = result.status != FileStatus.MISSING
                    file_valid = result.is_valid

            return EagleItem(
                id=item_data.get("id", ""),
                name=item_name,
                ext=item_ext,
                tags=item_data.get("tags", []),
                url=item_data.get("url"),
                annotation=item_data.get("annotation"),
                folders=item_data.get("folders", []),
                path=file_path,
                file_verified=file_verified,
                file_exists=file_exists,
                file_valid=file_valid,
            )
        except EagleIntegrationError:
            return None

    def get_item_file_path(self, item_id: str, ext: str = "") -> Optional[Path]:
        """
        Get the resolved file path for an Eagle item.

        Args:
            item_id: Eagle item ID
            ext: File extension (optional, will fetch if not provided)

        Returns:
            Resolved Path or None if not found
        """
        if not self.file_verifier:
            return None

        # Get extension from item if not provided
        if not ext:
            item = self.get_item(item_id, verify=False)
            if item:
                ext = item.ext

        if not ext:
            return None

        return self.file_verifier.resolve_eagle_path(item_id, ext)

    def verify_item_file(
        self,
        item_id: str
    ) -> Tuple[bool, Optional[Path], Optional[str]]:
        """
        Verify that an Eagle item has a valid file.

        Args:
            item_id: Eagle item ID

        Returns:
            Tuple of (is_valid, resolved_path, error_message)
        """
        item = self.get_item(item_id, verify=True)

        if not item:
            return False, None, f"Item {item_id} not found"

        if not item.file_verified:
            return False, None, "File verification not available"

        if not item.file_exists:
            return False, None, f"File missing for item {item_id}"

        if not item.file_valid:
            return False, Path(item.path) if item.path else None, "File is corrupt or invalid"

        return True, Path(item.path) if item.path else None, None

    def get_orphaned_items(
        self,
        limit: Optional[int] = None
    ) -> List[EagleItem]:
        """
        Find all items that don't have valid files.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of EagleItem objects without valid files
        """
        all_items = self.search(limit=limit, verify=True)
        return [item for item in all_items if not item.file_exists]

    def get_corrupt_items(
        self,
        limit: Optional[int] = None
    ) -> List[EagleItem]:
        """
        Find all items with corrupt files.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of EagleItem objects with corrupt files
        """
        all_items = self.search(limit=limit, verify=True)
        return [item for item in all_items if item.file_exists and not item.file_valid]

    def generate_library_health_report(self) -> Dict[str, Any]:
        """
        Generate a health report for the Eagle library.

        Returns:
            Dictionary with health statistics
        """
        all_items = self.search(verify=True)

        total = len(all_items)
        valid = sum(1 for item in all_items if item.file_valid)
        missing = sum(1 for item in all_items if not item.file_exists)
        corrupt = sum(1 for item in all_items if item.file_exists and not item.file_valid)
        unverified = sum(1 for item in all_items if not item.file_verified)

        return {
            "total_items": total,
            "valid_files": valid,
            "missing_files": missing,
            "corrupt_files": corrupt,
            "unverified": unverified,
            "health_percentage": (valid / total * 100) if total > 0 else 0,
            "missing_items": [
                {"id": item.id, "name": item.name}
                for item in all_items if not item.file_exists
            ][:50],  # Limit to first 50
            "corrupt_items": [
                {"id": item.id, "name": item.name, "path": item.path}
                for item in all_items if item.file_exists and not item.file_valid
            ][:50],
        }

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
