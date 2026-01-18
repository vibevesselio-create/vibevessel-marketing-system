#!/usr/bin/env python3
"""
VIBES Volume Reorganization Script
=================================

Reorganizes the /Volumes/VIBES/ volume according to production workflow specifications.
Implements phased approach: analysis → deduplication → migration → cleanup.

Phase 1: Analysis & Indexing (Current)
- Scan all music files
- Extract metadata (Artist, Album, Title, etc.)
- Generate audio fingerprints for deduplication
- Create comprehensive file index

Phase 2: Deduplication Planning
- Identify duplicate groups
- Determine best version to keep
- Create deduplication mapping

Phase 3: Directory Structure Creation
- Create target directory structure

Phase 4: File Migration (Dry Run)
- Simulate file moves
- Verify target paths

Phase 5: File Migration (Live)
- Execute file migration
- Handle edge cases

Phase 6: Cleanup & Verification
- Verify migration success
- Clean up empty directories
- Generate final report
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from collections import defaultdict
import hashlib

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/vibes_reorganization.log')
    ]
)
logger = logging.getLogger(__name__)

# Music file extensions
MUSIC_EXTENSIONS = {'.wav', '.m4a', '.flac', '.aiff', '.aif', '.mp3', '.alac'}

# Target directory structure
TARGET_MUSIC_DIR = Path("/Volumes/VIBES/Music/Automatically Add to Music.localized")
TARGET_BACKUP_DIR = Path("/Volumes/VIBES/Music-Backup")
TARGET_ARCHIVE_DIR = Path("/Volumes/VIBES/Music-Archive")

# 2026-01-16: New 3-file output structure directories
# Primary outputs: WAV+AIFF to Eagle Library (organized by playlist), WAV copy to playlist-tracks
PLAYLIST_TRACKS_DIR = Path(os.getenv("PLAYLIST_TRACKS_DIR", "/Volumes/SYSTEM_SSD/Dropbox/Music/playlists/playlist-tracks"))
# Note: M4A is no longer in the default output chain

def extract_metadata(file_path: Path) -> Dict[str, Any]:
    """
    Extract metadata from audio file.
    
    Returns:
        Dictionary with metadata fields (artist, album, title, etc.)
    """
    metadata = {
        'path': str(file_path),
        'filename': file_path.name,
        'extension': file_path.suffix.lower(),
        'size': file_path.stat().st_size,
        'modified': file_path.stat().st_mtime,
        'artist': None,
        'album': None,
        'title': None,
        'genre': None,
        'bpm': None,
        'key': None,
        'duration': None,
    }
    
    # Try to extract metadata using mutagen
    try:
        from mutagen import File as MutagenFile
        from mutagen.id3 import ID3NoHeaderError
        
        audio_file = MutagenFile(str(file_path))
        if audio_file is not None:
            # Extract common tags
            if 'TPE1' in audio_file or '©ART' in audio_file:
                artist = audio_file.get('TPE1', audio_file.get('©ART', ['']))
                metadata['artist'] = str(artist[0]) if isinstance(artist, list) else str(artist)
            
            if 'TALB' in audio_file or '©alb' in audio_file:
                album = audio_file.get('TALB', audio_file.get('©alb', ['']))
                metadata['album'] = str(album[0]) if isinstance(album, list) else str(album)
            
            if 'TIT2' in audio_file or '©nam' in audio_file:
                title = audio_file.get('TIT2', audio_file.get('©nam', ['']))
                metadata['title'] = str(title[0]) if isinstance(title, list) else str(title)
            
            if 'TCON' in audio_file or '©gen' in audio_file:
                genre = audio_file.get('TCON', audio_file.get('©gen', ['']))
                metadata['genre'] = str(genre[0]) if isinstance(genre, list) else str(genre)
            
            # Extract duration if available
            if hasattr(audio_file, 'info') and hasattr(audio_file.info, 'length'):
                metadata['duration'] = audio_file.info.length
            
    except ImportError:
        logger.warning("mutagen not available, skipping metadata extraction")
    except Exception as e:
        logger.debug(f"Error extracting metadata from {file_path}: {e}")
    
    # Fallback: Try to infer from filename/directory
    if not metadata['artist'] or not metadata['title']:
        # Try common patterns: "Artist - Title.ext" or "Title - Artist.ext"
        name_without_ext = file_path.stem
        if ' - ' in name_without_ext:
            parts = name_without_ext.split(' - ', 1)
            if not metadata['artist']:
                metadata['artist'] = parts[0].strip()
            if not metadata['title']:
                metadata['title'] = parts[1].strip()
    
    # Normalize unknown values
    if not metadata['artist']:
        metadata['artist'] = 'Unknown Artist'
    if not metadata['album']:
        metadata['album'] = 'Unknown Album'
    if not metadata['title']:
        metadata['title'] = file_path.stem
    
    return metadata

def generate_file_hash(file_path: Path) -> str:
    """Generate SHA256 hash of file for duplicate detection."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"Error generating hash for {file_path}: {e}")
        return ""

def scan_volume(root_path: Path, extract_metadata_flag: bool = True, checkpoint_file: Optional[Path] = None, resume: bool = False) -> Dict[str, Any]:
    """
    Scan volume for music files and extract metadata.
    
    Args:
        root_path: Root directory to scan
        extract_metadata_flag: Whether to extract metadata (slower but more complete)
        checkpoint_file: Optional path to checkpoint file for resume capability
        resume: Whether to resume from checkpoint
    
    Returns:
        Dictionary with scan results
    """
    logger.info(f"Starting volume scan: {root_path}")
    
    # Load checkpoint if resuming
    processed_paths = set()
    if resume and checkpoint_file and checkpoint_file.exists():
        try:
            logger.info(f"Resuming from checkpoint: {checkpoint_file}")
            with open(checkpoint_file, 'r') as f:
                checkpoint_data = json.load(f)
                processed_paths = set(checkpoint_data.get('processed_paths', []))
                logger.info(f"Resuming with {len(processed_paths)} already processed files")
        except Exception as e:
            logger.warning(f"Could not load checkpoint: {e}, starting fresh")
    
    all_files = []
    file_hashes = {}
    hash_to_files = defaultdict(list)
    directory_stats = defaultdict(lambda: {'files': 0, 'size': 0})
    
    total_size = 0
    files_processed = 0
    checkpoint_interval = 500  # Save checkpoint every N files
    
    try:
        for root, dirs, files in os.walk(root_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            root_path_obj = Path(root)
            
            for file_name in files:
                if file_name.startswith('.'):
                    continue
                
                file_path = root_path_obj / file_name
                
                # Skip if already processed (resume mode)
                if resume and str(file_path) in processed_paths:
                    continue
                
                ext = file_path.suffix.lower()
                
                if ext in MUSIC_EXTENSIONS:
                    try:
                        file_info = {
                            'path': str(file_path),
                            'directory': str(root_path_obj),
                            'filename': file_name,
                            'extension': ext,
                            'size': file_path.stat().st_size,
                            'modified': file_path.stat().st_mtime,
                        }
                        
                        # Extract metadata if requested
                        if extract_metadata_flag:
                            metadata = extract_metadata(file_path)
                            file_info.update(metadata)
                        
                        # Generate file hash for duplicate detection
                        file_hash = generate_file_hash(file_path)
                        file_info['hash'] = file_hash
                        
                        if file_hash:
                            hash_to_files[file_hash].append(file_info)
                        
                        all_files.append(file_info)
                        directory_stats[str(root_path_obj)]['files'] += 1
                        directory_stats[str(root_path_obj)]['size'] += file_path.stat().st_size
                        total_size += file_path.stat().st_size
                        files_processed += 1
                        processed_paths.add(str(file_path))
                        
                        # Save checkpoint periodically
                        if checkpoint_file and files_processed % checkpoint_interval == 0:
                            try:
                                checkpoint_data = {
                                    'processed_paths': list(processed_paths),
                                    'files_processed': files_processed,
                                    'timestamp': datetime.now().isoformat()
                                }
                                with open(checkpoint_file, 'w') as f:
                                    json.dump(checkpoint_data, f, indent=2)
                                logger.debug(f"Checkpoint saved: {files_processed} files processed")
                            except Exception as e:
                                logger.warning(f"Could not save checkpoint: {e}")
                        
                        if files_processed % 100 == 0:
                            logger.info(f"Processed {files_processed} files...")
                    
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Error processing {file_path}: {e}")
                        continue
    
    except KeyboardInterrupt:
        logger.warning("Scan interrupted by user")
        # Save final checkpoint on interrupt
        if checkpoint_file:
            try:
                checkpoint_data = {
                    'processed_paths': list(processed_paths),
                    'files_processed': files_processed,
                    'timestamp': datetime.now().isoformat(),
                    'interrupted': True
                }
                with open(checkpoint_file, 'w') as f:
                    json.dump(checkpoint_data, f, indent=2)
                logger.info(f"Checkpoint saved before exit: {files_processed} files processed")
            except Exception as e:
                logger.warning(f"Could not save final checkpoint: {e}")
    except Exception as e:
        logger.error(f"Error during scan: {e}", exc_info=True)
    
    # Identify duplicates
    duplicates = {h: files for h, files in hash_to_files.items() if len(files) > 1}
    
    logger.info(f"Scan complete: {files_processed} files, {len(duplicates)} duplicate groups")
    
    return {
        'timestamp': datetime.now().isoformat(),
        'root_path': str(root_path),
        'total_files': len(all_files),
        'total_size': total_size,
        'total_size_gb': round(total_size / (1024**3), 2),
        'duplicate_groups': len(duplicates),
        'files': all_files,
        'duplicates': duplicates,
        'directory_stats': dict(directory_stats),
    }

def determine_target_path(metadata: Dict[str, Any], file_type: str = 'm4a') -> Path:
    """
    Determine target path for file based on metadata.
    
    Args:
        metadata: File metadata dictionary
        file_type: File type ('m4a' for music, 'wav' for backup)
    
    Returns:
        Target Path object
    """
    artist = metadata.get('artist', 'Unknown Artist')
    album = metadata.get('album', 'Unknown Album')
    title = metadata.get('title', metadata.get('filename', 'Unknown'))
    extension = metadata.get('extension', '.m4a')
    
    # Sanitize path components
    def sanitize_path_component(component: str) -> str:
        # Remove invalid characters for macOS
        invalid_chars = ['/', ':', '<', '>', '"', '|', '?', '*']
        for char in invalid_chars:
            component = component.replace(char, '_')
        return component.strip()
    
    artist = sanitize_path_component(artist)
    album = sanitize_path_component(album)
    title = sanitize_path_component(title)
    
    # Determine base directory
    if file_type == 'wav':
        base_dir = TARGET_BACKUP_DIR
    else:
        base_dir = TARGET_MUSIC_DIR
    
    # Construct path
    target_path = base_dir / artist / album / f"{title}{extension}"
    
    return target_path

def main():
    """Main execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Reorganize VIBES volume')
    parser.add_argument('--phase', choices=['1', '2', '3', '4', '5', '6'], default='1',
                       help='Phase to execute')
    parser.add_argument('--dry-run', action='store_true',
                       help='Dry run mode (no actual file moves)')
    parser.add_argument('--no-metadata', action='store_true',
                       help='Skip metadata extraction (faster scan)')
    parser.add_argument('--output', type=str, default='logs/vibes_reorganization_index.json',
                       help='Output file for scan results')
    parser.add_argument('--checkpoint', type=str, default='logs/vibes_reorganization_checkpoint.json',
                       help='Checkpoint file for resume capability')
    parser.add_argument('--resume', action='store_true',
                       help='Resume from checkpoint file')
    
    args = parser.parse_args()
    
    root_path = Path("/Volumes/VIBES/")
    
    if not root_path.exists():
        logger.error(f"Volume not found: {root_path}")
        sys.exit(1)
    
    logger.info("=" * 80)
    logger.info("VIBES VOLUME REORGANIZATION")
    logger.info("=" * 80)
    logger.info(f"Phase: {args.phase}")
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info(f"Root Path: {root_path}")
    logger.info("")
    
    if args.phase == '1':
        # Phase 1: Analysis & Indexing
        logger.info("Phase 1: Analysis & Indexing")
        logger.info("This may take a while...")
        
        checkpoint_path = Path(args.checkpoint) if args.resume else None
        scan_results = scan_volume(
            root_path, 
            extract_metadata_flag=not args.no_metadata,
            checkpoint_file=checkpoint_path,
            resume=args.resume
        )
        
        # Save results
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(scan_results, f, indent=2, default=str)
        
        logger.info(f"Results saved to: {output_path}")
        logger.info(f"Total files: {scan_results['total_files']}")
        logger.info(f"Total size: {scan_results['total_size_gb']} GB")
        logger.info(f"Duplicate groups: {scan_results['duplicate_groups']}")
    
    else:
        logger.info(f"Phase {args.phase} not yet implemented")
        logger.info("Please run Phase 1 first to generate the index")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\nOperation interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
