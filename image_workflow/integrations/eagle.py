"""Eagle library integration.

Reads image metadata from Eagle library databases.
Eagle stores data in JSON files within the .library folder structure.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

from image_workflow.core.models import ImageInfo, ImageMetadata, SourceLocation, SourceType
from image_workflow.utils.errors import IntegrationError

logger = logging.getLogger(__name__)


@dataclass
class EagleImage:
    """Image data from Eagle library."""

    # Eagle identifiers
    id: str  # Eagle's unique ID
    name: str  # Display name

    # File information
    ext: str  # File extension
    file_path: Optional[str] = None
    size: Optional[int] = None

    # Timestamps
    btime: Optional[int] = None  # Birth time (creation)
    mtime: Optional[int] = None  # Modified time
    added_at: Optional[int] = None  # When added to Eagle

    # Dimensions
    width: Optional[int] = None
    height: Optional[int] = None

    # Metadata
    annotation: Optional[str] = None  # Notes
    url: Optional[str] = None  # Source URL if imported from web
    star: int = 0  # Rating (0-5)

    # Tags and folders
    tags: List[str] = field(default_factory=list)
    folders: List[str] = field(default_factory=list)

    # Color palette
    palettes: List[Dict] = field(default_factory=list)

    # EXIF subset
    last_modified: Optional[datetime] = None

    def to_image_info(self) -> ImageInfo:
        """Convert to standard ImageInfo model."""
        capture_time = None
        if self.btime:
            try:
                capture_time = datetime.fromtimestamp(self.btime / 1000)
            except (OSError, ValueError):
                pass

        metadata = ImageMetadata(
            filename=f"{self.name}.{self.ext}",
            width=self.width,
            height=self.height,
            capture_time=capture_time,
            rating=self.star,
            keywords=self.tags,
            collections=self.folders,
        )

        location = SourceLocation(
            source=SourceType.EAGLE,
            source_id=self.id,
            file_path=self.file_path,
            last_synced=datetime.now(),
        )

        return ImageInfo(
            uii="",  # Will be computed from content hash
            eagle_id=self.id,
            locations=[location],
            metadata=metadata,
            master_location=SourceType.EAGLE,
        )


class EagleLibraryReader:
    """Reads image data from Eagle library folders.

    Eagle libraries are folders with a .library extension containing:
    - images/ folder with image subfolders (one per image)
    - metadata.json in each image folder
    - tags.json at library root
    """

    def __init__(self, library_path: Union[str, Path]):
        """Initialize the library reader.

        Args:
            library_path: Path to the .library folder

        Raises:
            IntegrationError: If library cannot be opened
        """
        self.library_path = Path(library_path)

        if not self.library_path.exists():
            raise IntegrationError(f"Eagle library not found: {library_path}")

        if not self.library_path.suffix.lower() == '.library':
            raise IntegrationError(f"Not an Eagle library: {library_path}")

        self.images_path = self.library_path / 'images'
        if not self.images_path.exists():
            raise IntegrationError(f"No images folder in library: {library_path}")

        self._tags_cache: Optional[Dict[str, str]] = None
        self._folders_cache: Optional[Dict[str, str]] = None

    def get_image_count(self) -> int:
        """Get total number of images in the library."""
        count = 0
        for item in self.images_path.iterdir():
            if item.is_dir() and (item / 'metadata.json').exists():
                count += 1
        return count

    def get_all_tags(self) -> Dict[str, str]:
        """Get all tags from the library.

        Returns:
            Dict mapping tag ID to tag name
        """
        if self._tags_cache is not None:
            return self._tags_cache

        tags_file = self.library_path / 'tags.json'
        if not tags_file.exists():
            self._tags_cache = {}
            return self._tags_cache

        try:
            with open(tags_file, 'r', encoding='utf-8') as f:
                tags_data = json.load(f)

            self._tags_cache = {}
            self._parse_tags_recursive(tags_data, self._tags_cache)
            return self._tags_cache
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read tags.json: {e}")
            self._tags_cache = {}
            return self._tags_cache

    def _parse_tags_recursive(
        self,
        tags_list: List[Dict],
        result: Dict[str, str]
    ) -> None:
        """Recursively parse nested tags structure."""
        for tag in tags_list:
            tag_id = tag.get('id')
            tag_name = tag.get('name')
            if tag_id and tag_name:
                result[tag_id] = tag_name

            children = tag.get('children', [])
            if children:
                self._parse_tags_recursive(children, result)

    def get_all_folders(self) -> Dict[str, str]:
        """Get all folders from the library.

        Returns:
            Dict mapping folder ID to folder name
        """
        if self._folders_cache is not None:
            return self._folders_cache

        folders_file = self.library_path / 'folders.json'
        if not folders_file.exists():
            self._folders_cache = {}
            return self._folders_cache

        try:
            with open(folders_file, 'r', encoding='utf-8') as f:
                folders_data = json.load(f)

            self._folders_cache = {}
            self._parse_folders_recursive(folders_data, self._folders_cache)
            return self._folders_cache
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read folders.json: {e}")
            self._folders_cache = {}
            return self._folders_cache

    def _parse_folders_recursive(
        self,
        folders_list: List[Dict],
        result: Dict[str, str]
    ) -> None:
        """Recursively parse nested folders structure."""
        for folder in folders_list:
            folder_id = folder.get('id')
            folder_name = folder.get('name')
            if folder_id and folder_name:
                result[folder_id] = folder_name

            children = folder.get('children', [])
            if children:
                self._parse_folders_recursive(children, result)

    def get_all_images(
        self,
        limit: Optional[int] = None,
        include_tags: bool = True
    ) -> List[EagleImage]:
        """Get all images from the library.

        Args:
            limit: Maximum number of images to return
            include_tags: Whether to resolve tag IDs to names

        Returns:
            List of EagleImage objects
        """
        images = []
        tags_map = self.get_all_tags() if include_tags else {}
        folders_map = self.get_all_folders() if include_tags else {}

        for image_folder in self.images_path.iterdir():
            if limit and len(images) >= limit:
                break

            if not image_folder.is_dir():
                continue

            metadata_file = image_folder / 'metadata.json'
            if not metadata_file.exists():
                continue

            try:
                image = self._read_image_metadata(
                    image_folder,
                    tags_map,
                    folders_map
                )
                if image:
                    images.append(image)
            except Exception as e:
                logger.warning(f"Failed to read {image_folder.name}: {e}")

        logger.debug(f"Retrieved {len(images)} images from Eagle library")
        return images

    def iterate_images(
        self,
        batch_size: int = 1000,
        include_tags: bool = True
    ) -> Iterator[EagleImage]:
        """Iterate through all images.

        Args:
            batch_size: Images to process before yielding
            include_tags: Whether to resolve tag IDs to names

        Yields:
            EagleImage objects
        """
        tags_map = self.get_all_tags() if include_tags else {}
        folders_map = self.get_all_folders() if include_tags else {}
        count = 0

        for image_folder in self.images_path.iterdir():
            if not image_folder.is_dir():
                continue

            metadata_file = image_folder / 'metadata.json'
            if not metadata_file.exists():
                continue

            try:
                image = self._read_image_metadata(
                    image_folder,
                    tags_map,
                    folders_map
                )
                if image:
                    yield image
                    count += 1

                    if count % batch_size == 0:
                        logger.debug(f"Processed {count} images")
            except Exception as e:
                logger.warning(f"Failed to read {image_folder.name}: {e}")

    def get_image_by_id(self, eagle_id: str) -> Optional[EagleImage]:
        """Get a specific image by ID.

        Args:
            eagle_id: Eagle's unique image ID

        Returns:
            EagleImage or None if not found
        """
        # Eagle stores images in folders named by ID
        # Format: ID.info (e.g., "LZEFKH8YH1JR4.info")
        for image_folder in self.images_path.iterdir():
            if image_folder.name.startswith(eagle_id):
                tags_map = self.get_all_tags()
                folders_map = self.get_all_folders()
                return self._read_image_metadata(
                    image_folder,
                    tags_map,
                    folders_map
                )

        return None

    def _read_image_metadata(
        self,
        image_folder: Path,
        tags_map: Dict[str, str],
        folders_map: Dict[str, str]
    ) -> Optional[EagleImage]:
        """Read metadata for a single image."""
        metadata_file = image_folder / 'metadata.json'

        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read metadata: {e}")
            return None

        # Resolve tag IDs to names
        tag_ids = data.get('tags', [])
        tag_names = [tags_map.get(tid, tid) for tid in tag_ids]

        # Resolve folder IDs to names
        folder_ids = data.get('folders', [])
        folder_names = [folders_map.get(fid, fid) for fid in folder_ids]

        # Find the actual image file
        file_path = None
        ext = data.get('ext', '')
        for f in image_folder.iterdir():
            if f.suffix.lower() == f'.{ext.lower()}':
                file_path = str(f)
                break

        return EagleImage(
            id=data.get('id', ''),
            name=data.get('name', ''),
            ext=ext,
            file_path=file_path,
            size=data.get('size'),
            btime=data.get('btime'),
            mtime=data.get('mtime'),
            added_at=data.get('modificationTime'),
            width=data.get('width'),
            height=data.get('height'),
            annotation=data.get('annotation'),
            url=data.get('url'),
            star=data.get('star', 0),
            tags=tag_names,
            folders=folder_names,
            palettes=data.get('palettes', []),
        )

    def get_image_file_path(self, eagle_id: str) -> Optional[Path]:
        """Get the actual file path for an image.

        Args:
            eagle_id: Eagle's unique image ID

        Returns:
            Path to the image file or None if not found
        """
        image = self.get_image_by_id(eagle_id)
        if image and image.file_path:
            return Path(image.file_path)
        return None
