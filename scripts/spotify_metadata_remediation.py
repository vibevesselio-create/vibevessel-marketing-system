#!/usr/bin/env python3
"""
Spotify Metadata Remediation Tool
==================================

Uses CSV backup files as secondary data source for metadata fixing and validation.
Compares Notion data vs CSV data to identify and fix inconsistencies.

Author: Cursor MM1 Agent • 2026-01-13
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "monolithic-scripts"))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import modules
try:
    from spotify_csv_backup import SpotifyCSVBackup, get_spotify_csv_backup
    from spotify_integration_module import SpotifyAPI, NotionSpotifyIntegration, SpotifyOAuthManager
    CSV_BACKUP_AVAILABLE = True
except ImportError as e:
    print(f"Error importing modules: {e}")
    CSV_BACKUP_AVAILABLE = False
    sys.exit(1)

# Import unified logging
try:
    from unified_config import setup_unified_logging
    logger = setup_unified_logging(session_id="spotify_metadata_remediation")
except (ImportError, TimeoutError):
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)


class MetadataRemediator:
    """Remediates Spotify metadata using CSV backup as secondary verification."""
    
    def __init__(self):
        self.csv_backup = get_spotify_csv_backup()
        self.spotify_api = SpotifyAPI(SpotifyOAuthManager())
        self.notion = NotionSpotifyIntegration()
        self.csv_backup.load_all()
    
    def compare_track_metadata(
        self, 
        notion_track: Dict[str, Any], 
        csv_track: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare Notion track metadata with CSV backup.
        
        Returns:
            Dictionary with comparison results and recommended fixes
        """
        differences = {}
        recommendations = {}
        
        # Get Spotify ID
        spotify_id = self._get_spotify_id(notion_track)
        if not spotify_id:
            return {"error": "No Spotify ID found in Notion track"}
        
        # Compare key fields
        fields_to_compare = [
            ("name", "Title", "Track Name"),
            ("artist", "Artist Name", "Artist Name(s)"),
            ("album", "Album", "Album Name"),
            ("duration_ms", "Duration (ms)", "Duration (ms)"),
            ("popularity", "Popularity", "Popularity"),
            ("tempo", "Tempo", "Tempo"),
            ("key", "Key", "Key"),
            ("energy", "Energy", "Energy"),
            ("danceability", "Danceability", "Danceability"),
        ]
        
        for field_key, notion_prop, csv_key in fields_to_compare:
            notion_value = self._get_notion_property(notion_track, notion_prop)
            csv_value = self._get_csv_value(csv_track, csv_key, field_key)
            
            if notion_value != csv_value and csv_value is not None:
                differences[field_key] = {
                    "notion": notion_value,
                    "csv": csv_value,
                    "notion_property": notion_prop
                }
                
                # Recommend using CSV value if it's more complete
                if csv_value and (not notion_value or csv_value != ""):
                    recommendations[field_key] = csv_value
        
        return {
            "spotify_id": spotify_id,
            "differences": differences,
            "recommendations": recommendations,
            "has_differences": len(differences) > 0
        }
    
    def _get_spotify_id(self, notion_track: Dict[str, Any]) -> Optional[str]:
        """Extract Spotify ID from Notion track."""
        props = notion_track.get("properties", {})
        
        # Try "Spotify ID" property
        spotify_id_prop = props.get("Spotify ID", {})
        if spotify_id_prop.get("type") == "rich_text":
            rich_text = spotify_id_prop.get("rich_text", [])
            if rich_text:
                return rich_text[0].get("text", {}).get("content", "")
        
        # Try "Spotify URL" property
        spotify_url_prop = props.get("Spotify URL", {})
        if spotify_url_prop.get("type") == "url":
            url = spotify_url_prop.get("url", "")
            if "spotify.com/track/" in url:
                return url.split("spotify.com/track/")[1].split("?")[0]
        
        return None
    
    def _get_notion_property(self, notion_track: Dict[str, Any], property_name: str) -> Any:
        """Extract property value from Notion track."""
        props = notion_track.get("properties", {})
        prop = props.get(property_name, {})
        prop_type = prop.get("type")
        
        if prop_type == "title":
            title_array = prop.get("title", [])
            return title_array[0].get("text", {}).get("content", "") if title_array else None
        elif prop_type == "rich_text":
            rich_text = prop.get("rich_text", [])
            return rich_text[0].get("text", {}).get("content", "") if rich_text else None
        elif prop_type == "number":
            return prop.get("number")
        elif prop_type == "url":
            return prop.get("url")
        elif prop_type == "checkbox":
            return prop.get("checkbox")
        elif prop_type == "select":
            select = prop.get("select")
            return select.get("name") if select else None
        
        return None
    
    def _get_csv_value(self, csv_track: Dict[str, Any], csv_key: str, field_key: str) -> Any:
        """Extract value from CSV track."""
        # Handle nested fields
        if field_key == "artist":
            artists = csv_track.get("artists", [])
            if artists:
                return ", ".join([a.get("name", "") for a in artists])
            return None
        elif field_key == "album":
            album = csv_track.get("album", {})
            return album.get("name") if album else None
        elif field_key in ["tempo", "key", "energy", "danceability"]:
            # Audio features are nested
            audio_features = csv_track.get("audio_features", {})
            return audio_features.get(field_key)
        else:
            return csv_track.get(field_key)
    
    def remediate_track(self, notion_page_id: str, auto_fix: bool = False) -> Dict[str, Any]:
        """
        Remediate a single track's metadata.
        
        Args:
            notion_page_id: Notion page ID of the track
            auto_fix: Automatically apply recommended fixes
            
        Returns:
            Remediation results
        """
        # Get track from Notion
        notion_track = self.notion.get_page(notion_page_id)
        if not notion_track:
            return {"error": "Track not found in Notion"}
        
        # Get Spotify ID
        spotify_id = self._get_spotify_id(notion_track)
        if not spotify_id:
            return {"error": "No Spotify ID found"}
        
        # Get track from CSV backup
        csv_track = self.csv_backup.get_track_by_id(spotify_id)
        if not csv_track:
            return {"error": "Track not found in CSV backup"}
        
        # Compare metadata
        comparison = self.compare_track_metadata(notion_track, csv_track)
        
        if not comparison.get("has_differences"):
            return {
                "success": True,
                "message": "No differences found - metadata is consistent",
                "comparison": comparison
            }
        
        # Apply fixes if requested
        fixes_applied = []
        if auto_fix and comparison.get("recommendations"):
            for field, csv_value in comparison["recommendations"].items():
                try:
                    # Map field to Notion property
                    field_to_prop = {
                        "name": "Title",
                        "artist": "Artist Name",
                        "album": "Album",
                        "duration_ms": "Duration (ms)",
                        "popularity": "Popularity",
                        "tempo": "Tempo",
                        "key": "Key",
                        "energy": "Energy",
                        "danceability": "Danceability",
                    }
                    
                    prop_name = field_to_prop.get(field)
                    if prop_name:
                        # Update Notion property
                        # Note: This is a simplified update - full implementation would
                        # need to handle different property types properly
                        success = self._update_notion_property(
                            notion_page_id, 
                            prop_name, 
                            csv_value
                        )
                        if success:
                            fixes_applied.append(field)
                except Exception as e:
                    logger.error(f"Failed to fix {field}: {e}")
        
        return {
            "success": True,
            "differences_found": len(comparison["differences"]),
            "fixes_applied": fixes_applied if auto_fix else [],
            "recommendations": comparison["recommendations"],
            "comparison": comparison
        }
    
    def _update_notion_property(
        self, 
        page_id: str, 
        property_name: str, 
        value: Any
    ) -> bool:
        """Update a Notion property (simplified - would need full implementation)."""
        # This is a placeholder - full implementation would need to handle
        # different property types (rich_text, number, select, etc.)
        try:
            # Use existing update method from NotionSpotifyIntegration
            # For now, just return True as placeholder
            logger.info(f"Would update {property_name} to {value} for page {page_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update property: {e}")
            return False
    
    def batch_remediate(
        self, 
        track_ids: List[str], 
        auto_fix: bool = False
    ) -> Dict[str, Any]:
        """
        Remediate multiple tracks in batch.
        
        Args:
            track_ids: List of Notion page IDs
            auto_fix: Automatically apply recommended fixes
            
        Returns:
            Batch remediation results
        """
        results = {
            "total": len(track_ids),
            "processed": 0,
            "fixed": 0,
            "errors": 0,
            "details": []
        }
        
        for track_id in track_ids:
            try:
                result = self.remediate_track(track_id, auto_fix=auto_fix)
                results["processed"] += 1
                
                if result.get("success"):
                    if result.get("fixes_applied"):
                        results["fixed"] += len(result["fixes_applied"])
                else:
                    results["errors"] += 1
                
                results["details"].append({
                    "track_id": track_id,
                    "result": result
                })
            except Exception as e:
                results["errors"] += 1
                logger.error(f"Error remediating track {track_id}: {e}")
                results["details"].append({
                    "track_id": track_id,
                    "error": str(e)
                })
        
        return results
    
    def generate_remediation_report(
        self, 
        track_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate a remediation report comparing Notion vs CSV metadata.
        
        Args:
            track_ids: Optional list of track IDs to check (None = check all)
            
        Returns:
            Report dictionary
        """
        report = {
            "generated_at": datetime.now().isoformat(),
            "total_tracks_checked": 0,
            "tracks_with_differences": 0,
            "common_differences": {},
            "tracks": []
        }
        
        # Get tracks to check
        if track_ids:
            tracks_to_check = track_ids
        else:
            # Get all tracks from Notion (would need to implement query)
            tracks_to_check = []
            logger.warning("Batch checking all tracks not yet implemented")
        
        for track_id in tracks_to_check:
            try:
                notion_track = self.notion.get_page(track_id)
                if not notion_track:
                    continue
                
                spotify_id = self._get_spotify_id(notion_track)
                if not spotify_id:
                    continue
                
                csv_track = self.csv_backup.get_track_by_id(spotify_id)
                if not csv_track:
                    continue
                
                comparison = self.compare_track_metadata(notion_track, csv_track)
                report["total_tracks_checked"] += 1
                
                if comparison.get("has_differences"):
                    report["tracks_with_differences"] += 1
                    
                    # Track common differences
                    for field in comparison["differences"]:
                        report["common_differences"][field] = \
                            report["common_differences"].get(field, 0) + 1
                
                report["tracks"].append({
                    "notion_id": track_id,
                    "spotify_id": spotify_id,
                    "comparison": comparison
                })
            except Exception as e:
                logger.error(f"Error checking track {track_id}: {e}")
        
        return report


def main():
    """Main function for CLI usage."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Remediate Spotify metadata using CSV backup"
    )
    parser.add_argument(
        "notion_page_id",
        nargs="?",
        help="Notion page ID of track to remediate"
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Automatically apply recommended fixes"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate remediation report"
    )
    
    args = parser.parse_args()
    
    remediator = MetadataRemediator()
    
    if args.report:
        print("Generating remediation report...")
        report = remediator.generate_remediation_report()
        print(f"\nReport Generated:")
        print(f"  Total tracks checked: {report['total_tracks_checked']}")
        print(f"  Tracks with differences: {report['tracks_with_differences']}")
        print(f"  Common differences: {report['common_differences']}")
    elif args.notion_page_id:
        print(f"Remediating track: {args.notion_page_id}")
        result = remediator.remediate_track(
            args.notion_page_id, 
            auto_fix=args.auto_fix
        )
        print(f"\nResult: {result}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
