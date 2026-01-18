#!/usr/bin/env python3
"""
Lightroom to Google Drive SQL Sync
==================================

Synchronizes Adobe Lightroom Classic catalog data to a SQLite database
stored in Google Drive for the vibe.vessel.io@gmail.com account.

Success Criteria:
- Full synchronization of Lightroom library to SQL database
- Database stored in Google Drive for cloud access
- Includes: images, EXIF metadata, collections, keywords, develop settings

Database: lightroom_library_sync.db
Location: Google Drive/VibeVessel/Databases/lightroom_library_sync.db

Author: Claude Code Agent
Date: 2026-01-18
"""

import os
import sys
import sqlite3
import shutil
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import hashlib

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configuration
LIGHTROOM_CATALOG_PATH = "/Volumes/SYSTEM_SSD/master-lightroom-2/Master_Lightroom.lrcat"
GOOGLE_DRIVE_PATH = "/Users/brianhellemn/Library/CloudStorage/GoogleDrive-vibe.vessel.io@gmail.com/My Drive"
OUTPUT_DB_DIR = f"{GOOGLE_DRIVE_PATH}/VibeVessel/Databases"
OUTPUT_DB_NAME = "lightroom_library_sync.db"
OUTPUT_DB_PATH = f"{OUTPUT_DB_DIR}/{OUTPUT_DB_NAME}"

# Backup configuration
LOCAL_BACKUP_DIR = "/Users/brianhellemn/Projects/github-production/data/lightroom_sync_backups"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"lightroom_sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class LightroomImage:
    """Represents a Lightroom image with full metadata."""
    id_local: int
    id_global: str
    capture_time: Optional[str]
    rating: Optional[int]
    color_labels: str
    file_format: str
    file_height: Optional[float]
    file_width: Optional[float]
    pick: int
    orientation: Optional[str]
    # File info
    file_name: str
    file_extension: str
    original_filename: str
    folder_path: str
    # EXIF data
    aperture: Optional[float]
    focal_length: Optional[float]
    iso: Optional[int]
    shutter_speed: Optional[float]
    gps_latitude: Optional[float]
    gps_longitude: Optional[float]
    camera_model: Optional[str]
    lens_model: Optional[str]
    # IPTC data
    city: Optional[str]
    country: Optional[str]
    creator: Optional[str]
    # Collections
    collections: List[str] = None

    def __post_init__(self):
        if self.collections is None:
            self.collections = []


class LightroomCatalogReader:
    """Reads data from Lightroom Classic catalog SQLite database."""

    def __init__(self, catalog_path: str):
        self.catalog_path = Path(catalog_path)
        if not self.catalog_path.exists():
            raise FileNotFoundError(f"Lightroom catalog not found: {catalog_path}")

        self.conn = None

    def connect(self) -> sqlite3.Connection:
        """Connect to the Lightroom catalog database (read-only)."""
        if self.conn is None:
            # Open in read-only mode to be safe
            uri = f"file:{self.catalog_path}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True)
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_catalog_stats(self) -> Dict[str, int]:
        """Get basic catalog statistics."""
        conn = self.connect()
        cursor = conn.cursor()

        stats = {}

        # Total images
        cursor.execute("SELECT COUNT(*) FROM Adobe_images")
        stats['total_images'] = cursor.fetchone()[0]

        # Images with EXIF
        cursor.execute("SELECT COUNT(*) FROM AgHarvestedExifMetadata")
        stats['images_with_exif'] = cursor.fetchone()[0]

        # Collections
        cursor.execute("SELECT COUNT(*) FROM AgLibraryCollection WHERE (systemOnly IS NULL OR systemOnly = 0)")
        stats['collections'] = cursor.fetchone()[0]

        # Folders
        cursor.execute("SELECT COUNT(*) FROM AgLibraryFolder")
        stats['folders'] = cursor.fetchone()[0]

        # Keywords
        cursor.execute("SELECT COUNT(*) FROM AgLibraryKeyword")
        stats['keywords'] = cursor.fetchone()[0]

        return stats

    def get_all_images(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all images with full metadata."""
        conn = self.connect()
        cursor = conn.cursor()

        query = """
        SELECT
            i.id_local,
            i.id_global,
            i.captureTime,
            i.rating,
            i.colorLabels,
            i.fileFormat,
            i.fileHeight,
            i.fileWidth,
            i.pick,
            i.orientation,
            f.baseName,
            f.extension,
            f.originalFilename,
            folder.pathFromRoot,
            exif.aperture,
            exif.focalLength,
            exif.isoSpeedRating,
            exif.shutterSpeed,
            exif.gpsLatitude,
            exif.gpsLongitude,
            cam.value as camera_model,
            lens.value as lens_model,
            iptc_city.value as city,
            iptc_country.value as country,
            iptc_creator.value as creator
        FROM Adobe_images i
        JOIN AgLibraryFile f ON i.rootFile = f.id_local
        LEFT JOIN AgLibraryFolder folder ON f.folder = folder.id_local
        LEFT JOIN AgHarvestedExifMetadata exif ON i.id_local = exif.image
        LEFT JOIN AgInternedExifCameraModel cam ON exif.cameraModelRef = cam.id_local
        LEFT JOIN AgInternedExifLens lens ON exif.lensRef = lens.id_local
        LEFT JOIN AgHarvestedIptcMetadata iptc ON i.id_local = iptc.image
        LEFT JOIN AgInternedIptcCity iptc_city ON iptc.cityRef = iptc_city.id_local
        LEFT JOIN AgInternedIptcCountry iptc_country ON iptc.countryRef = iptc_country.id_local
        LEFT JOIN AgInternedIptcCreator iptc_creator ON iptc.creatorRef = iptc_creator.id_local
        ORDER BY i.captureTime DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)

        images = []
        for row in cursor.fetchall():
            images.append({
                'id_local': row['id_local'],
                'id_global': row['id_global'],
                'capture_time': row['captureTime'],
                'rating': row['rating'],
                'color_labels': row['colorLabels'] or '',
                'file_format': row['fileFormat'],
                'file_height': row['fileHeight'],
                'file_width': row['fileWidth'],
                'pick': row['pick'] or 0,
                'orientation': row['orientation'],
                'file_name': row['baseName'],
                'file_extension': row['extension'],
                'original_filename': row['originalFilename'],
                'folder_path': row['pathFromRoot'] or '',
                'aperture': row['aperture'],
                'focal_length': row['focalLength'],
                'iso': int(row['isoSpeedRating']) if row['isoSpeedRating'] else None,
                'shutter_speed': row['shutterSpeed'],
                'gps_latitude': row['gpsLatitude'],
                'gps_longitude': row['gpsLongitude'],
                'camera_model': row['camera_model'],
                'lens_model': row['lens_model'],
                'city': row['city'],
                'country': row['country'],
                'creator': row['creator'],
            })

        return images

    def get_collections(self) -> List[Dict[str, Any]]:
        """Get all collections with image counts."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            c.id_local,
            c.name,
            c.creationId,
            c.parent,
            (SELECT COUNT(*) FROM AgLibraryCollectionImage ci WHERE ci.collection = c.id_local) as image_count
        FROM AgLibraryCollection c
        WHERE c.systemOnly IS NULL OR c.systemOnly = 0
        ORDER BY c.name
        """)

        collections = []
        for row in cursor.fetchall():
            collections.append({
                'id_local': row['id_local'],
                'name': row['name'],
                'creation_id': row['creationId'],
                'parent_id': row['parent'],
                'image_count': row['image_count'],
            })

        return collections

    def get_collection_images(self, collection_id: int) -> List[int]:
        """Get image IDs in a collection."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT image FROM AgLibraryCollectionImage
        WHERE collection = ?
        """, (collection_id,))

        return [row['image'] for row in cursor.fetchall()]

    def get_keywords(self) -> List[Dict[str, Any]]:
        """Get all keywords with hierarchy."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            k.id_local,
            k.name,
            k.parent,
            k.lc_name
        FROM AgLibraryKeyword k
        ORDER BY k.name
        """)

        keywords = []
        for row in cursor.fetchall():
            keywords.append({
                'id_local': row['id_local'],
                'name': row['name'],
                'parent_id': row['parent'],
                'lowercase_name': row['lc_name'],
            })

        return keywords

    def get_image_keywords(self, image_id: int) -> List[str]:
        """Get keywords for a specific image."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT k.name
        FROM AgLibraryKeyword k
        JOIN AgLibraryKeywordImage ki ON k.id_local = ki.tag
        WHERE ki.image = ?
        """, (image_id,))

        return [row['name'] for row in cursor.fetchall()]

    def get_folders(self) -> List[Dict[str, Any]]:
        """Get all folders in the catalog."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            f.id_local,
            f.pathFromRoot,
            r.absolutePath as root_path,
            r.name as root_name
        FROM AgLibraryFolder f
        LEFT JOIN AgLibraryRootFolder r ON f.rootFolder = r.id_local
        ORDER BY f.pathFromRoot
        """)

        folders = []
        for row in cursor.fetchall():
            folders.append({
                'id_local': row['id_local'],
                'path_from_root': row['pathFromRoot'],
                'root_path': row['root_path'],
                'root_name': row['root_name'],
            })

        return folders


class GoogleDriveSQLSync:
    """Manages the sync database in Google Drive."""

    def __init__(self, db_path: str, backup_dir: str):
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.conn = None

    def ensure_directories(self):
        """Ensure output and backup directories exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def backup_existing(self):
        """Backup existing database before sync."""
        if self.db_path.exists():
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = self.backup_dir / f"lightroom_library_sync_{timestamp}.db"
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"Backed up existing database to {backup_path}")

            # Keep only last 5 backups
            backups = sorted(self.backup_dir.glob("lightroom_library_sync_*.db"))
            if len(backups) > 5:
                for old_backup in backups[:-5]:
                    old_backup.unlink()
                    logger.info(f"Removed old backup: {old_backup}")

    def connect(self) -> sqlite3.Connection:
        """Connect to the sync database."""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def initialize_schema(self):
        """Create database schema if not exists."""
        conn = self.connect()
        cursor = conn.cursor()

        # Images table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY,
            lr_id_local INTEGER UNIQUE NOT NULL,
            lr_id_global TEXT UNIQUE NOT NULL,
            capture_time TEXT,
            rating INTEGER,
            color_labels TEXT,
            file_format TEXT,
            file_height REAL,
            file_width REAL,
            pick INTEGER DEFAULT 0,
            orientation TEXT,
            file_name TEXT,
            file_extension TEXT,
            original_filename TEXT,
            folder_path TEXT,
            full_path TEXT,
            aperture REAL,
            focal_length REAL,
            iso INTEGER,
            shutter_speed REAL,
            gps_latitude REAL,
            gps_longitude REAL,
            camera_model TEXT,
            lens_model TEXT,
            city TEXT,
            country TEXT,
            creator TEXT,
            sync_timestamp TEXT NOT NULL,
            checksum TEXT
        )
        """)

        # Collections table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY,
            lr_id_local INTEGER UNIQUE NOT NULL,
            name TEXT NOT NULL,
            creation_id TEXT,
            parent_id INTEGER,
            image_count INTEGER DEFAULT 0,
            sync_timestamp TEXT NOT NULL
        )
        """)

        # Collection-Image junction table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection_images (
            collection_id INTEGER NOT NULL,
            image_id INTEGER NOT NULL,
            PRIMARY KEY (collection_id, image_id),
            FOREIGN KEY (collection_id) REFERENCES collections(lr_id_local),
            FOREIGN KEY (image_id) REFERENCES images(lr_id_local)
        )
        """)

        # Keywords table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY,
            lr_id_local INTEGER UNIQUE NOT NULL,
            name TEXT NOT NULL,
            parent_id INTEGER,
            lowercase_name TEXT,
            sync_timestamp TEXT NOT NULL
        )
        """)

        # Image-Keyword junction table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS image_keywords (
            image_id INTEGER NOT NULL,
            keyword_id INTEGER NOT NULL,
            PRIMARY KEY (image_id, keyword_id),
            FOREIGN KEY (image_id) REFERENCES images(lr_id_local),
            FOREIGN KEY (keyword_id) REFERENCES keywords(lr_id_local)
        )
        """)

        # Folders table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY,
            lr_id_local INTEGER UNIQUE NOT NULL,
            path_from_root TEXT,
            root_path TEXT,
            root_name TEXT,
            sync_timestamp TEXT NOT NULL
        )
        """)

        # Sync metadata table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_metadata (
            id INTEGER PRIMARY KEY,
            sync_timestamp TEXT NOT NULL,
            source_catalog TEXT NOT NULL,
            total_images INTEGER,
            total_collections INTEGER,
            total_keywords INTEGER,
            total_folders INTEGER,
            sync_duration_seconds REAL,
            status TEXT
        )
        """)

        # Create indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_capture_time ON images(capture_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_rating ON images(rating)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_camera ON images(camera_model)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_folder ON images(folder_path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_format ON images(file_format)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_collections_name ON collections(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords_name ON keywords(name)")

        conn.commit()
        logger.info("Database schema initialized")

    def sync_images(self, images: List[Dict[str, Any]], timestamp: str):
        """Sync images to the database."""
        conn = self.connect()
        cursor = conn.cursor()

        # Clear existing images (full sync)
        cursor.execute("DELETE FROM images")

        for img in images:
            # Build full path
            full_path = f"{img['folder_path']}{img['file_name']}.{img['file_extension']}"

            # Generate checksum for change detection
            checksum_data = f"{img['id_global']}|{img['capture_time']}|{img['rating']}|{img['file_name']}"
            checksum = hashlib.md5(checksum_data.encode()).hexdigest()

            cursor.execute("""
            INSERT INTO images (
                lr_id_local, lr_id_global, capture_time, rating, color_labels,
                file_format, file_height, file_width, pick, orientation,
                file_name, file_extension, original_filename, folder_path, full_path,
                aperture, focal_length, iso, shutter_speed,
                gps_latitude, gps_longitude, camera_model, lens_model,
                city, country, creator, sync_timestamp, checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                img['id_local'], img['id_global'], img['capture_time'], img['rating'], img['color_labels'],
                img['file_format'], img['file_height'], img['file_width'], img['pick'], img['orientation'],
                img['file_name'], img['file_extension'], img['original_filename'], img['folder_path'], full_path,
                img['aperture'], img['focal_length'], img['iso'], img['shutter_speed'],
                img['gps_latitude'], img['gps_longitude'], img['camera_model'], img['lens_model'],
                img['city'], img['country'], img['creator'], timestamp, checksum
            ))

        conn.commit()
        logger.info(f"Synced {len(images)} images")

    def sync_collections(self, collections: List[Dict[str, Any]], timestamp: str):
        """Sync collections to the database."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM collections")

        for coll in collections:
            cursor.execute("""
            INSERT INTO collections (
                lr_id_local, name, creation_id, parent_id, image_count, sync_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                coll['id_local'], coll['name'], coll['creation_id'],
                coll['parent_id'], coll['image_count'], timestamp
            ))

        conn.commit()
        logger.info(f"Synced {len(collections)} collections")

    def sync_collection_images(self, collection_id: int, image_ids: List[int]):
        """Sync collection-image relationships."""
        conn = self.connect()
        cursor = conn.cursor()

        for image_id in image_ids:
            cursor.execute("""
            INSERT OR IGNORE INTO collection_images (collection_id, image_id)
            VALUES (?, ?)
            """, (collection_id, image_id))

        conn.commit()

    def sync_keywords(self, keywords: List[Dict[str, Any]], timestamp: str):
        """Sync keywords to the database."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM keywords")

        synced_count = 0
        for kw in keywords:
            # Skip keywords with no name
            if not kw.get('name'):
                continue
            cursor.execute("""
            INSERT INTO keywords (
                lr_id_local, name, parent_id, lowercase_name, sync_timestamp
            ) VALUES (?, ?, ?, ?, ?)
            """, (
                kw['id_local'], kw['name'], kw['parent_id'],
                kw['lowercase_name'], timestamp
            ))
            synced_count += 1

        conn.commit()
        logger.info(f"Synced {len(keywords)} keywords")

    def sync_folders(self, folders: List[Dict[str, Any]], timestamp: str):
        """Sync folders to the database."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM folders")

        for folder in folders:
            cursor.execute("""
            INSERT INTO folders (
                lr_id_local, path_from_root, root_path, root_name, sync_timestamp
            ) VALUES (?, ?, ?, ?, ?)
            """, (
                folder['id_local'], folder['path_from_root'],
                folder['root_path'], folder['root_name'], timestamp
            ))

        conn.commit()
        logger.info(f"Synced {len(folders)} folders")

    def record_sync_metadata(self, source_catalog: str, stats: Dict[str, int],
                             duration: float, status: str, timestamp: str):
        """Record sync operation metadata."""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO sync_metadata (
            sync_timestamp, source_catalog, total_images, total_collections,
            total_keywords, total_folders, sync_duration_seconds, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, source_catalog, stats.get('total_images', 0),
            stats.get('collections', 0), stats.get('keywords', 0),
            stats.get('folders', 0), duration, status
        ))

        conn.commit()


def run_full_sync(catalog_path: str = LIGHTROOM_CATALOG_PATH,
                  output_db_path: str = OUTPUT_DB_PATH,
                  backup_dir: str = LOCAL_BACKUP_DIR) -> Dict[str, Any]:
    """
    Run a full synchronization from Lightroom catalog to Google Drive SQL database.

    Args:
        catalog_path: Path to Lightroom catalog (.lrcat file)
        output_db_path: Path to output SQLite database in Google Drive
        backup_dir: Directory for local backups

    Returns:
        Dictionary with sync results and statistics
    """
    start_time = datetime.now()
    timestamp = start_time.isoformat()

    logger.info("=" * 60)
    logger.info("Starting Lightroom to Google Drive SQL Sync")
    logger.info(f"Source catalog: {catalog_path}")
    logger.info(f"Output database: {output_db_path}")
    logger.info("=" * 60)

    results = {
        'success': False,
        'start_time': timestamp,
        'source_catalog': catalog_path,
        'output_database': output_db_path,
        'stats': {},
        'errors': []
    }

    try:
        # Initialize catalog reader
        logger.info("Connecting to Lightroom catalog...")
        reader = LightroomCatalogReader(catalog_path)

        # Get catalog statistics
        stats = reader.get_catalog_stats()
        results['stats'] = stats
        logger.info(f"Catalog statistics: {json.dumps(stats, indent=2)}")

        # Initialize sync database
        logger.info("Initializing sync database...")
        sync_db = GoogleDriveSQLSync(output_db_path, backup_dir)
        sync_db.ensure_directories()
        sync_db.backup_existing()
        sync_db.initialize_schema()

        # Sync images
        logger.info("Fetching images from catalog...")
        images = reader.get_all_images()
        logger.info(f"Found {len(images)} images")
        sync_db.sync_images(images, timestamp)

        # Sync collections
        logger.info("Fetching collections...")
        collections = reader.get_collections()
        logger.info(f"Found {len(collections)} collections")
        sync_db.sync_collections(collections, timestamp)

        # Sync collection-image relationships
        logger.info("Syncing collection-image relationships...")
        for coll in collections:
            image_ids = reader.get_collection_images(coll['id_local'])
            sync_db.sync_collection_images(coll['id_local'], image_ids)

        # Sync keywords
        logger.info("Fetching keywords...")
        keywords = reader.get_keywords()
        logger.info(f"Found {len(keywords)} keywords")
        sync_db.sync_keywords(keywords, timestamp)

        # Sync folders
        logger.info("Fetching folders...")
        folders = reader.get_folders()
        logger.info(f"Found {len(folders)} folders")
        sync_db.sync_folders(folders, timestamp)

        # Calculate duration
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Record sync metadata
        sync_db.record_sync_metadata(
            source_catalog=catalog_path,
            stats=stats,
            duration=duration,
            status='success',
            timestamp=timestamp
        )

        # Close connections
        reader.close()
        sync_db.close()

        results['success'] = True
        results['duration_seconds'] = duration
        results['end_time'] = end_time.isoformat()

        logger.info("=" * 60)
        logger.info("SYNC COMPLETED SUCCESSFULLY")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Images synced: {len(images)}")
        logger.info(f"Collections synced: {len(collections)}")
        logger.info(f"Keywords synced: {len(keywords)}")
        logger.info(f"Folders synced: {len(folders)}")
        logger.info(f"Database location: {output_db_path}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        results['errors'].append(str(e))
        import traceback
        logger.error(traceback.format_exc())

    return results


def verify_google_drive_sync(db_path: str = OUTPUT_DB_PATH) -> Dict[str, Any]:
    """
    Verify the sync database in Google Drive.

    Returns:
        Dictionary with verification results
    """
    db_path = Path(db_path)

    results = {
        'exists': db_path.exists(),
        'path': str(db_path),
        'size_mb': 0,
        'tables': {},
        'last_sync': None
    }

    if not db_path.exists():
        logger.warning(f"Database not found: {db_path}")
        return results

    results['size_mb'] = db_path.stat().st_size / (1024 * 1024)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get table counts
        for table in ['images', 'collections', 'keywords', 'folders']:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            results['tables'][table] = cursor.fetchone()[0]

        # Get last sync info
        cursor.execute("""
        SELECT sync_timestamp, total_images, status, sync_duration_seconds
        FROM sync_metadata
        ORDER BY sync_timestamp DESC
        LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            results['last_sync'] = {
                'timestamp': row['sync_timestamp'],
                'total_images': row['total_images'],
                'status': row['status'],
                'duration_seconds': row['sync_duration_seconds']
            }

        conn.close()

        logger.info("=" * 60)
        logger.info("SYNC DATABASE VERIFICATION")
        logger.info(f"Path: {db_path}")
        logger.info(f"Size: {results['size_mb']:.2f} MB")
        logger.info(f"Images: {results['tables'].get('images', 0)}")
        logger.info(f"Collections: {results['tables'].get('collections', 0)}")
        logger.info(f"Keywords: {results['tables'].get('keywords', 0)}")
        logger.info(f"Folders: {results['tables'].get('folders', 0)}")
        if results['last_sync']:
            logger.info(f"Last sync: {results['last_sync']['timestamp']}")
            logger.info(f"Last sync status: {results['last_sync']['status']}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        results['error'] = str(e)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Lightroom to Google Drive SQL Sync")
    parser.add_argument("--catalog", default=LIGHTROOM_CATALOG_PATH,
                        help="Path to Lightroom catalog")
    parser.add_argument("--output", default=OUTPUT_DB_PATH,
                        help="Path to output SQLite database")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only verify existing sync database")

    args = parser.parse_args()

    if args.verify_only:
        results = verify_google_drive_sync(args.output)
    else:
        results = run_full_sync(args.catalog, args.output)

    print(json.dumps(results, indent=2, default=str))
