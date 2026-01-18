"""Adobe Lightroom Classic catalog integration.

Reads image metadata from Lightroom .lrcat SQLite databases.
Aligned with music_workflow patterns for consistent architecture.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

from image_workflow.core.models import ImageInfo, ImageMetadata, SourceLocation, SourceType
from image_workflow.utils.errors import IntegrationError

logger = logging.getLogger(__name__)


@dataclass
class LightroomImage:
    """Image data from Lightroom catalog."""

    # Lightroom identifiers
    id_local: int
    id_global: str  # UUID from Lightroom

    # File information
    file_name: str
    file_path: Optional[str] = None
    original_filename: Optional[str] = None

    # Capture metadata
    capture_time: Optional[datetime] = None
    rating: int = 0
    pick: int = 0  # -1=rejected, 0=unflagged, 1=picked
    color_label: Optional[str] = None

    # Technical metadata
    width: Optional[int] = None
    height: Optional[int] = None
    orientation: Optional[str] = None
    aspect_ratio: Optional[str] = None

    # EXIF data
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens: Optional[str] = None
    focal_length: Optional[float] = None
    aperture: Optional[float] = None
    shutter_speed: Optional[str] = None
    iso: Optional[int] = None

    # GPS data
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None

    # Keywords and collections
    keywords: List[str] = field(default_factory=list)
    collections: List[str] = field(default_factory=list)

    def to_image_info(self) -> ImageInfo:
        """Convert to standard ImageInfo model."""
        metadata = ImageMetadata(
            filename=self.file_name,
            original_filename=self.original_filename,
            width=self.width,
            height=self.height,
            capture_time=self.capture_time,
            camera_make=self.camera_make,
            camera_model=self.camera_model,
            lens=self.lens,
            focal_length=self.focal_length,
            aperture=self.aperture,
            iso=self.iso,
            gps_latitude=self.gps_latitude,
            gps_longitude=self.gps_longitude,
            rating=self.rating,
            keywords=self.keywords,
            collections=self.collections,
        )

        location = SourceLocation(
            source=SourceType.LIGHTROOM,
            source_id=self.id_global,
            file_path=self.file_path,
            last_synced=datetime.now(),
        )

        return ImageInfo(
            uii="",  # Will be computed from content hash
            lightroom_id=self.id_global,
            locations=[location],
            metadata=metadata,
            master_location=SourceType.LIGHTROOM,
        )


class LightroomCatalogReader:
    """Reads image data from Lightroom Classic catalogs.

    Supports reading from .lrcat SQLite database files.
    Aligned with music_workflow patterns for consistent integration behavior.
    """

    # SQL queries for extracting data
    IMAGES_QUERY = """
        SELECT
            ai.id_local,
            ai.id_global,
            arf.baseName as file_name,
            arf.originalFilename,
            ai.captureTime as capture_time,
            ai.rating,
            ai.pick,
            ai.colorLabels as color_label,
            arf.sidecarExtensions
        FROM Adobe_images ai
        LEFT JOIN AgLibraryFile arf ON ai.rootFile = arf.id_local
        WHERE ai.masterImage IS NULL
    """

    EXIF_QUERY = """
        SELECT
            image,
            cameraModelRef,
            cameraSNRef,
            lensRef,
            focalLength,
            aperture,
            isoSpeedRating,
            shutterSpeed,
            gpsLatitude,
            gpsLongitude,
            dateDay,
            dateMonth,
            dateYear,
            hasGPS
        FROM AgHarvestedExifMetadata
        WHERE image = ?
    """

    DIMENSIONS_QUERY = """
        SELECT
            image,
            croppedWidth,
            croppedHeight,
            orientation
        FROM AgHarvestedIptcMetadata
        WHERE image = ?
    """

    KEYWORDS_QUERY = """
        SELECT k.name
        FROM AgLibraryKeyword k
        JOIN AgLibraryKeywordImage ki ON k.id_local = ki.tag
        WHERE ki.image = ?
    """

    COLLECTIONS_QUERY = """
        SELECT c.name
        FROM AgLibraryCollection c
        JOIN AgLibraryCollectionImage ci ON c.id_local = ci.collection
        WHERE ci.image = ?
    """

    FOLDER_PATH_QUERY = """
        SELECT
            rf.absolutePath || f.pathFromRoot as folder_path
        FROM AgLibraryFile alf
        JOIN AgLibraryFolder f ON alf.folder = f.id_local
        JOIN AgLibraryRootFolder rf ON f.rootFolder = rf.id_local
        WHERE alf.id_local = (
            SELECT rootFile FROM Adobe_images WHERE id_local = ?
        )
    """

    def __init__(self, catalog_path: Union[str, Path]):
        """Initialize the catalog reader.

        Args:
            catalog_path: Path to the .lrcat file

        Raises:
            IntegrationError: If catalog cannot be opened
        """
        self.catalog_path = Path(catalog_path)

        if not self.catalog_path.exists():
            raise IntegrationError(f"Lightroom catalog not found: {catalog_path}")

        if not self.catalog_path.suffix.lower() == '.lrcat':
            raise IntegrationError(f"Not a Lightroom catalog: {catalog_path}")

        self._connection: Optional[sqlite3.Connection] = None

    def __enter__(self) -> 'LightroomCatalogReader':
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def connect(self) -> None:
        """Open connection to the catalog database."""
        try:
            self._connection = sqlite3.connect(
                f"file:{self.catalog_path}?mode=ro",
                uri=True
            )
            self._connection.row_factory = sqlite3.Row
            logger.info(f"Connected to Lightroom catalog: {self.catalog_path.name}")
        except sqlite3.Error as e:
            raise IntegrationError(f"Failed to open catalog: {e}")

    def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.debug("Closed Lightroom catalog connection")

    @property
    def connection(self) -> sqlite3.Connection:
        """Get the active database connection."""
        if not self._connection:
            raise IntegrationError("Not connected to catalog")
        return self._connection

    def get_image_count(self) -> int:
        """Get total number of images in the catalog."""
        cursor = self.connection.execute(
            "SELECT COUNT(*) FROM Adobe_images WHERE masterImage IS NULL"
        )
        return cursor.fetchone()[0]

    def get_collection_count(self) -> int:
        """Get total number of collections in the catalog."""
        cursor = self.connection.execute(
            "SELECT COUNT(*) FROM AgLibraryCollection"
        )
        return cursor.fetchone()[0]

    def get_keyword_count(self) -> int:
        """Get total number of keywords in the catalog."""
        cursor = self.connection.execute(
            "SELECT COUNT(*) FROM AgLibraryKeyword WHERE name IS NOT NULL"
        )
        return cursor.fetchone()[0]

    def get_all_images(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        include_metadata: bool = True
    ) -> List[LightroomImage]:
        """Get all images from the catalog.

        Args:
            limit: Maximum number of images to return
            offset: Number of images to skip
            include_metadata: Whether to include EXIF, keywords, etc.

        Returns:
            List of LightroomImage objects
        """
        query = self.IMAGES_QUERY

        if limit:
            query += f" LIMIT {limit}"
        if offset:
            query += f" OFFSET {offset}"

        cursor = self.connection.execute(query)
        images = []

        for row in cursor:
            image = self._row_to_image(dict(row))

            if include_metadata:
                self._enrich_metadata(image)

            images.append(image)

        logger.debug(f"Retrieved {len(images)} images from catalog")
        return images

    def iterate_images(
        self,
        batch_size: int = 1000,
        include_metadata: bool = True
    ) -> Iterator[LightroomImage]:
        """Iterate through all images in batches.

        Args:
            batch_size: Number of images per batch
            include_metadata: Whether to include EXIF, keywords, etc.

        Yields:
            LightroomImage objects
        """
        offset = 0
        total = self.get_image_count()

        while offset < total:
            images = self.get_all_images(
                limit=batch_size,
                offset=offset,
                include_metadata=include_metadata
            )

            for image in images:
                yield image

            offset += batch_size
            logger.debug(f"Processed {min(offset, total)}/{total} images")

    def get_image_by_id(
        self,
        id_local: int = None,
        id_global: str = None
    ) -> Optional[LightroomImage]:
        """Get a specific image by ID.

        Args:
            id_local: Local database ID
            id_global: Global UUID

        Returns:
            LightroomImage or None if not found
        """
        if id_local:
            query = self.IMAGES_QUERY + " AND ai.id_local = ?"
            cursor = self.connection.execute(query, (id_local,))
        elif id_global:
            query = self.IMAGES_QUERY + " AND ai.id_global = ?"
            cursor = self.connection.execute(query, (id_global,))
        else:
            raise ValueError("Must provide id_local or id_global")

        row = cursor.fetchone()
        if not row:
            return None

        image = self._row_to_image(dict(row))
        self._enrich_metadata(image)
        return image

    def get_all_collections(self) -> List[Dict[str, Any]]:
        """Get all collections from the catalog."""
        cursor = self.connection.execute("""
            SELECT
                id_local,
                name,
                creationId,
                parent
            FROM AgLibraryCollection
            WHERE name IS NOT NULL
        """)

        return [dict(row) for row in cursor]

    def get_all_keywords(self) -> List[Dict[str, Any]]:
        """Get all keywords from the catalog."""
        cursor = self.connection.execute("""
            SELECT
                id_local,
                name,
                lc_name,
                parent
            FROM AgLibraryKeyword
            WHERE name IS NOT NULL
        """)

        return [dict(row) for row in cursor]

    def get_all_folders(self) -> List[Dict[str, Any]]:
        """Get all folders from the catalog."""
        cursor = self.connection.execute("""
            SELECT
                f.id_local,
                f.pathFromRoot,
                rf.absolutePath as root_path,
                rf.name as root_name
            FROM AgLibraryFolder f
            JOIN AgLibraryRootFolder rf ON f.rootFolder = rf.id_local
        """)

        return [dict(row) for row in cursor]

    def _row_to_image(self, row: Dict) -> LightroomImage:
        """Convert a database row to LightroomImage."""
        capture_time = None
        if row.get('capture_time'):
            try:
                capture_time = datetime.fromisoformat(row['capture_time'])
            except (ValueError, TypeError):
                pass

        return LightroomImage(
            id_local=row['id_local'],
            id_global=row['id_global'],
            file_name=row['file_name'] or '',
            original_filename=row.get('originalFilename'),
            capture_time=capture_time,
            rating=row.get('rating') or 0,
            pick=row.get('pick') or 0,
            color_label=row.get('color_label'),
        )

    def _enrich_metadata(self, image: LightroomImage) -> None:
        """Add EXIF, keywords, and other metadata to an image."""
        # Get EXIF data
        cursor = self.connection.execute(self.EXIF_QUERY, (image.id_local,))
        exif_row = cursor.fetchone()
        if exif_row:
            exif = dict(exif_row)
            image.focal_length = exif.get('focalLength')
            image.aperture = exif.get('aperture')
            image.iso = exif.get('isoSpeedRating')
            image.shutter_speed = exif.get('shutterSpeed')
            image.gps_latitude = exif.get('gpsLatitude')
            image.gps_longitude = exif.get('gpsLongitude')

        # Get dimensions
        cursor = self.connection.execute(self.DIMENSIONS_QUERY, (image.id_local,))
        dim_row = cursor.fetchone()
        if dim_row:
            dims = dict(dim_row)
            image.width = dims.get('croppedWidth')
            image.height = dims.get('croppedHeight')
            image.orientation = dims.get('orientation')

        # Get keywords
        cursor = self.connection.execute(self.KEYWORDS_QUERY, (image.id_local,))
        image.keywords = [row[0] for row in cursor if row[0]]

        # Get collections
        cursor = self.connection.execute(self.COLLECTIONS_QUERY, (image.id_local,))
        image.collections = [row[0] for row in cursor if row[0]]

        # Get folder path
        cursor = self.connection.execute(self.FOLDER_PATH_QUERY, (image.id_local,))
        folder_row = cursor.fetchone()
        if folder_row and folder_row[0]:
            folder_path = folder_row[0]
            image.file_path = f"{folder_path}/{image.file_name}"
