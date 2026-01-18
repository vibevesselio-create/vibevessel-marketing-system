#!/usr/bin/env python3
"""
VIBES Volume Analysis for Music Reorganization
==============================================

Scans /Volumes/VIBES/ and identifies:
1. Folders containing "Music" in name
2. Folders containing music files (.wav, .m4a, .flac, .aiff)
3. Comprehensive indexing of all music files
4. Current directory structure analysis
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
from datetime import datetime
from collections import defaultdict

MUSIC_EXTENSIONS = {'.wav', '.m4a', '.flac', '.aiff', '.aif', '.mp3', '.alac'}
MUSIC_NAME_KEYWORDS = ['music', 'Music', 'MUSIC']

def find_music_directories(root_path: Path) -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
    """Find all directories with Music in name or containing music files."""
    music_by_name = {}  # Directories with "Music" in name
    music_by_content = {}  # Directories containing music files
    all_files = []  # All music files found
    directory_stats = defaultdict(lambda: {'files': 0, 'size': 0, 'extensions': set()})
    
    print(f"Scanning {root_path}...")
    
    try:
        for root, dirs, files in os.walk(root_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            root_path_obj = Path(root)
            
            # Check if folder name contains "Music"
            if any(keyword in root_path_obj.name for keyword in MUSIC_NAME_KEYWORDS):
                if str(root_path_obj) not in music_by_name:
                    music_by_name[str(root_path_obj)] = {
                        'path': str(root_path_obj),
                        'name': root_path_obj.name,
                        'depth': len(root_path_obj.parts),
                        'file_count': 0,
                        'size': 0,
                        'extensions': set()
                    }
            
            # Check for music files
            music_files_in_dir = []
            total_size = 0
            extensions = set()
            
            for file_name in files:
                if file_name.startswith('.'):
                    continue
                
                file_path = root_path_obj / file_name
                ext = file_path.suffix.lower()
                
                if ext in MUSIC_EXTENSIONS:
                    try:
                        size = file_path.stat().st_size
                        music_files_in_dir.append({
                            'path': str(file_path),
                            'name': file_name,
                            'size': size,
                            'extension': ext
                        })
                        all_files.append({
                            'path': str(file_path),
                            'name': file_name,
                            'directory': str(root_path_obj),
                            'size': size,
                            'extension': ext,
                            'modified': file_path.stat().st_mtime
                        })
                        total_size += size
                        extensions.add(ext)
                        directory_stats[str(root_path_obj)]['files'] += 1
                        directory_stats[str(root_path_obj)]['size'] += size
                        directory_stats[str(root_path_obj)]['extensions'].add(ext)
                    except (OSError, PermissionError) as e:
                        continue
            
            # If directory contains music files, add it
            if music_files_in_dir:
                if str(root_path_obj) not in music_by_content:
                    music_by_content[str(root_path_obj)] = {
                        'path': str(root_path_obj),
                        'name': root_path_obj.name,
                        'depth': len(root_path_obj.parts),
                        'files': music_files_in_dir,
                        'file_count': len(music_files_in_dir),
                        'total_size': total_size,
                        'extensions': list(extensions)
                    }
                
                # Also mark parent if name contains Music
                if any(keyword in root_path_obj.name for keyword in MUSIC_NAME_KEYWORDS):
                    if str(root_path_obj) in music_by_name:
                        music_by_name[str(root_path_obj)]['file_count'] = len(music_files_in_dir)
                        music_by_name[str(root_path_obj)]['size'] = total_size
                        music_by_name[str(root_path_obj)]['extensions'] = list(extensions)
    
    except PermissionError as e:
        print(f"Permission error: {e}")
    except Exception as e:
        print(f"Error scanning: {e}")
    
    return {
        'by_name': music_by_name,
        'by_content': music_by_content,
        'all_files': all_files,
        'stats': dict(directory_stats)
    }, directory_stats

def analyze_directory_structure(music_dirs: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze the directory structure for patterns."""
    analysis = {
        'total_directories_with_music_name': len(music_dirs['by_name']),
        'total_directories_with_music_files': len(music_dirs['by_content']),
        'total_music_files': len(music_dirs['all_files']),
        'total_size_bytes': sum(f['size'] for f in music_dirs['all_files']),
        'by_extension': defaultdict(int),
        'by_depth': defaultdict(int),
        'largest_directories': [],
        'directory_patterns': defaultdict(int)
    }
    
    # Extension breakdown
    for file_info in music_dirs['all_files']:
        analysis['by_extension'][file_info['extension']] += 1
    
    # Depth analysis
    for dir_info in music_dirs['by_content'].values():
        depth = dir_info['depth']
        analysis['by_depth'][depth] += 1
    
    # Largest directories
    dirs_with_size = []
    for path, dir_info in music_dirs['by_content'].items():
        dirs_with_size.append({
            'path': path,
            'size': dir_info['total_size'],
            'file_count': dir_info['file_count']
        })
    analysis['largest_directories'] = sorted(dirs_with_size, key=lambda x: x['size'], reverse=True)[:20]
    
    # Pattern analysis (extract common patterns from paths)
    for path in music_dirs['by_content'].keys():
        parts = Path(path).parts
        if len(parts) >= 4:  # /Volumes/VIBES/[category]/[subcategory]
            pattern = '/'.join(parts[2:4])  # Skip /Volumes/VIBES
            analysis['directory_patterns'][pattern] += 1
    
    return analysis

def generate_report(scan_results: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive report."""
    report = {
        'timestamp': datetime.now().isoformat(),
        'volume_path': '/Volumes/VIBES/',
        'scan_summary': {
            'directories_with_music_name': analysis['total_directories_with_music_name'],
            'directories_with_music_files': analysis['total_directories_with_music_files'],
            'total_music_files': analysis['total_music_files'],
            'total_size_gb': round(analysis['total_size_bytes'] / (1024**3), 2),
            'total_size_bytes': analysis['total_size_bytes']
        },
        'file_breakdown': dict(analysis['by_extension']),
        'directory_depth_distribution': dict(analysis['by_depth']),
        'top_20_largest_directories': analysis['largest_directories'],
        'directory_patterns': dict(analysis['directory_patterns']),
        'all_music_directories': {
            'by_name': list(scan_results['by_name'].keys()),
            'by_content': {k: {
                'path': v['path'],
                'file_count': v['file_count'],
                'size_gb': round(v['total_size'] / (1024**3), 2),
                'extensions': v['extensions']
            } for k, v in scan_results['by_content'].items()}
        },
        'sample_files': scan_results['all_files'][:100] if len(scan_results['all_files']) > 100 else scan_results['all_files']
    }
    
    return report

def main():
    """Main execution"""
    print("=" * 80)
    print("VIBES VOLUME ANALYSIS FOR MUSIC REORGANIZATION")
    print("=" * 80)
    print()
    
    root_path = Path("/Volumes/VIBES/")
    
    if not root_path.exists():
        print(f"❌ Volume not found: {root_path}")
        sys.exit(1)
    
    print(f"Scanning volume: {root_path}")
    print("This may take several minutes...")
    print()
    
    # Scan for music directories
    scan_results, stats = find_music_directories(root_path)
    
    print(f"\n✓ Scan complete")
    print(f"  Directories with 'Music' in name: {len(scan_results['by_name'])}")
    print(f"  Directories with music files: {len(scan_results['by_content'])}")
    print(f"  Total music files found: {len(scan_results['all_files'])}")
    
    # Analyze structure
    print("\nAnalyzing directory structure...")
    analysis = analyze_directory_structure(scan_results)
    
    # Generate report
    report = generate_report(scan_results, analysis)
    
    # Save report
    report_file = Path("logs/vibes_volume_analysis_report.json")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    
    with report_file.open("w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n✓ Report saved to: {report_file}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("ANALYSIS SUMMARY")
    print("=" * 80)
    print(f"Total directories with 'Music' in name: {report['scan_summary']['directories_with_music_name']}")
    print(f"Total directories with music files: {report['scan_summary']['directories_with_music_files']}")
    print(f"Total music files: {report['scan_summary']['total_music_files']}")
    print(f"Total size: {report['scan_summary']['total_size_gb']} GB")
    print(f"\nFile breakdown by extension:")
    for ext, count in sorted(report['file_breakdown'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {ext}: {count:,} files")
    
    print(f"\nTop 10 largest directories:")
    for i, dir_info in enumerate(report['top_20_largest_directories'][:10], 1):
        print(f"  {i}. {dir_info['path']}")
        print(f"     {dir_info['file_count']} files, {round(dir_info['size']/(1024**3), 2)} GB")
    
    return report

if __name__ == "__main__":
    try:
        report = main()
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\nScan interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
