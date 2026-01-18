#!/usr/bin/env python3
"""
Download both audio and video from a YouTube URL using yt-dlp.
This script downloads the best quality video and audio separately, then merges them.
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    print("ERROR: yt-dlp is not installed. Please install it with: pip install yt-dlp")
    sys.exit(1)


def download_youtube_audio_video(url: str, output_dir: Path = None, keep_video: bool = True, keep_audio: bool = True):
    """
    Download both audio and video from a YouTube URL.
    
    Args:
        url: YouTube URL to download
        output_dir: Directory to save files (default: current directory)
        keep_video: Whether to keep the separate video file
        keep_audio: Whether to keep the separate audio file
    """
    if output_dir is None:
        output_dir = Path.cwd()
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📥 Downloading from: {url}")
    print(f"📁 Output directory: {output_dir}")
    
    # Common yt-dlp options
    ffmpeg_location = "/opt/homebrew/bin/ffmpeg"
    if not os.path.exists(ffmpeg_location):
        ffmpeg_location = "ffmpeg"  # Try system PATH
    
    ydl_common = {
        "quiet": False,
        "no_warnings": False,
        "ffmpeg_location": ffmpeg_location,
    }
    
    # First, extract info to get the title
    print("\n🔍 Extracting video information...")
    try:
        with yt_dlp.YoutubeDL({**ydl_common, "extract_flat": False}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'video')
            video_id = info.get('id', 'unknown')
            print(f"✅ Found: {title}")
            print(f"   Video ID: {video_id}")
    except Exception as e:
        print(f"❌ Failed to extract video information: {e}")
        return False
    
    # Clean title for filename
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_title = safe_title.replace(' ', '_')[:100]  # Limit length
    
    # Download merged video+audio (best quality)
    print(f"\n📹 Downloading merged video+audio (best quality)...")
    merged_output = output_dir / f"{safe_title}.%(ext)s"
    
    ydl_opts_merged = {
        **ydl_common,
        "format": "bestvideo+bestaudio/best",  # Best video + best audio, merged
        "outtmpl": str(merged_output),
        "merge_output_format": "mp4",  # Merge to MP4
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts_merged) as ydl:
            ydl.download([url])
        print(f"✅ Merged video+audio downloaded successfully")
        
        # Find the downloaded file
        merged_files = list(output_dir.glob(f"{safe_title}.*"))
        if merged_files:
            print(f"   📄 File: {merged_files[0]}")
    except Exception as e:
        print(f"❌ Failed to download merged video: {e}")
        return False
    
    # Download separate audio file (FULL QUALITY WAV)
    if keep_audio:
        print(f"\n🎵 Downloading separate audio file in FULL QUALITY WAV format...")
        audio_output = output_dir / f"{safe_title}_audio.%(ext)s"
        
        ydl_opts_audio = {
            **ydl_common,
            "format": "bestaudio/best",  # Get the best audio quality available
            "outtmpl": str(audio_output),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",  # WAV format (lossless)
                "preferredquality": "0",  # Highest quality (0 = best)
            }],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
                ydl.download([url])
            print(f"✅ Audio file downloaded successfully")
            
            # Find the downloaded file
            audio_files = list(output_dir.glob(f"{safe_title}_audio.*"))
            if audio_files:
                print(f"   📄 File: {audio_files[0]}")
        except Exception as e:
            print(f"⚠️  Failed to download separate audio: {e}")
    
    # Download separate video file (best quality, no audio)
    if keep_video:
        print(f"\n🎬 Downloading separate video file (no audio)...")
        video_output = output_dir / f"{safe_title}_video.%(ext)s"
        
        ydl_opts_video = {
            **ydl_common,
            "format": "bestvideo[ext=mp4]/bestvideo",
            "outtmpl": str(video_output),
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts_video) as ydl:
                ydl.download([url])
            print(f"✅ Video file downloaded successfully")
            
            # Find the downloaded file
            video_files = list(output_dir.glob(f"{safe_title}_video.*"))
            if video_files:
                print(f"   📄 File: {video_files[0]}")
        except Exception as e:
            print(f"⚠️  Failed to download separate video: {e}")
    
    print(f"\n✅ Download complete!")
    print(f"📁 Files saved to: {output_dir}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Download both audio and video from a YouTube URL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 download_youtube_audio_video.py "https://youtu.be/gWbJTzmDMO0"
  python3 download_youtube_audio_video.py "https://youtu.be/gWbJTzmDMO0" --output-dir ~/Downloads
  python3 download_youtube_audio_video.py "https://youtu.be/gWbJTzmDMO0" --no-separate-files
        """
    )
    parser.add_argument("url", help="YouTube URL to download")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: current directory)"
    )
    parser.add_argument(
        "--no-separate-files",
        action="store_true",
        help="Only download merged video+audio, skip separate audio/video files"
    )
    
    args = parser.parse_args()
    
    keep_separate = not args.no_separate_files
    
    success = download_youtube_audio_video(
        url=args.url,
        output_dir=args.output_dir,
        keep_video=keep_separate,
        keep_audio=keep_separate,
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

