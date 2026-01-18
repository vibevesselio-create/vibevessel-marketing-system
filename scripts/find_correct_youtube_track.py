#!/usr/bin/env python3
"""
Find the correct YouTube URL for a Spotify track by matching duration.
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "monolithic-scripts"))

from dotenv import load_dotenv
load_dotenv()

# Import YouTube search
import importlib.util
import sys
spec = importlib.util.spec_from_file_location(
    "soundcloud_download_prod_merge_2",
    project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
)
module = importlib.util.module_from_spec(spec)
# Fix Python 3.13 @dataclass compatibility - register module before exec
sys.modules[spec.name] = module
spec.loader.exec_module(module)

from spotify_integration_module import SpotifyAPI

def search_youtube_with_duration(artist, title, target_duration_ms, max_results=10):
    """Search YouTube and filter by duration."""
    import yt_dlp
    
    search_query = f"{artist} {title}"
    print(f"🔍 Searching YouTube for: {search_query}")
    print(f"   Target duration: {target_duration_ms} ms ({target_duration_ms/1000:.1f} seconds)")
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'default_search': 'ytsearch',
        'max_downloads': max_results,
    }
    
    results = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch{max_results}:{search_query}", download=False)
            if info and 'entries' in info:
                for entry in info['entries']:
                    if entry:
                        duration = entry.get('duration', 0)
                        url = entry.get('url') or entry.get('webpage_url') or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                        title_full = entry.get('title', 'Unknown')
                        
                        duration_diff = abs(duration - (target_duration_ms / 1000))
                        results.append({
                            'url': url,
                            'title': title_full,
                            'duration': duration,
                            'duration_diff': duration_diff
                        })
        except Exception as e:
            print(f"Error searching: {e}")
    
    # Sort by duration difference
    results.sort(key=lambda x: x['duration_diff'])
    
    return results

def main():
    spotify = SpotifyAPI()
    track_id = "4cPeIoEz3nKshMqLKgTAfw"
    
    print("Fetching Spotify track details...")
    track_data = spotify.get_track_info(track_id)
    
    if not track_data:
        print("❌ Failed to fetch track data")
        return 1
    
    title = track_data.get('name', '')
    artist = ', '.join([a.get('name', '') for a in track_data.get('artists', [])])
    duration_ms = track_data.get('duration_ms', 0)
    
    print(f"\n✅ CORRECT TRACK:")
    print(f"   Title: {title}")
    print(f"   Artist: {artist}")
    print(f"   Duration: {duration_ms} ms ({duration_ms/1000:.1f} seconds / {duration_ms/60000:.1f} minutes)")
    
    print(f"\n🔍 Searching YouTube for matching duration...")
    results = search_youtube_with_duration(artist, title, duration_ms, max_results=20)
    
    if results:
        print(f"\n📊 Top 5 matches:")
        for i, result in enumerate(results[:5], 1):
            print(f"\n{i}. {result['title']}")
            print(f"   Duration: {result['duration']:.1f}s ({result['duration']/60:.1f}m)")
            print(f"   Difference: {result['duration_diff']:.1f}s")
            print(f"   URL: {result['url']}")
        
        best_match = results[0]
        if best_match['duration_diff'] < 10:  # Within 10 seconds
            print(f"\n✅ BEST MATCH FOUND:")
            print(f"   URL: {best_match['url']}")
            print(f"\nTo update Notion, run:")
            print(f"   python3 scripts/update_youtube_url.py 2e6e7361-6c27-8007-b3f6-e8f46b9e8233 '{best_match['url']}'")
            return 0
        else:
            print(f"\n⚠️  No close match found (best difference: {best_match['duration_diff']:.1f}s)")
            return 1
    else:
        print("\n❌ No YouTube results found")
        return 1

if __name__ == '__main__':
    sys.exit(main())
