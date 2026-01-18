#!/usr/bin/env python3
"""
Create Notion Issue for VIBES Volume Reorganization
===================================================

Creates a comprehensive issue in the Issues+Questions database for multi-agent
coordination of the VIBES volume music reorganization project.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from unified_config import load_unified_env, get_unified_config
from shared_core.notion.token_manager import get_notion_client
from shared_core.notion.issues_questions import ISSUES_QUESTIONS_DB_ID, create_issue_or_question

def load_analysis_report() -> Dict[str, Any]:
    """Load the VIBES volume analysis report."""
    report_file = project_root / "logs/vibes_volume_analysis_report.json"
    
    if not report_file.exists():
        raise FileNotFoundError(f"Analysis report not found: {report_file}")
    
    with report_file.open() as f:
        return json.load(f)

def generate_issue_content(report: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive issue content for Notion."""
    
    scan_summary = report['scan_summary']
    file_breakdown = report['file_breakdown']
    top_dirs = report['top_20_largest_directories']
    patterns = report['directory_patterns']
    
    # Build comprehensive description
    description_parts = []
    
    description_parts.append("## Executive Summary")
    description_parts.append("")
    description_parts.append("This issue tracks the comprehensive reorganization, deduplication, and cleanup of the `/Volumes/VIBES/` volume to align with the established music workflow system documented in the marketing system. The volume contains **670.24 GB** of music files across **20,148 files** in **7,578 directories** that need to be reorganized according to the production workflow specifications.")
    description_parts.append("")
    
    description_parts.append("## Current State Analysis")
    description_parts.append("")
    description_parts.append("### Volume Scan Results")
    description_parts.append(f"- **Total Directories with 'Music' in name:** {scan_summary['directories_with_music_name']}")
    description_parts.append(f"- **Total Directories containing music files:** {scan_summary['directories_with_music_files']}")
    description_parts.append(f"- **Total Music Files:** {scan_summary['total_music_files']:,}")
    description_parts.append(f"- **Total Size:** {scan_summary['total_size_gb']} GB ({scan_summary['total_size_bytes']:,} bytes)")
    description_parts.append("")
    
    description_parts.append("### File Format Breakdown")
    for ext, count in sorted(file_breakdown.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / scan_summary['total_music_files']) * 100
        description_parts.append(f"- **{ext}**: {count:,} files ({percentage:.1f}%)")
    description_parts.append("")
    
    description_parts.append("### Top 10 Largest Directories")
    for i, dir_info in enumerate(top_dirs[:10], 1):
        size_gb = dir_info['size'] / (1024**3)
        description_parts.append(f"{i}. `{dir_info['path']}`")
        description_parts.append(f"   - {dir_info['file_count']:,} files, {size_gb:.2f} GB")
    description_parts.append("")
    
    description_parts.append("### Current Directory Structure Issues")
    description_parts.append("")
    description_parts.append("The current structure shows significant fragmentation:")
    description_parts.append("")
    description_parts.append("1. **Multiple Auto-Import Directories**:")
    description_parts.append("   - `/Volumes/VIBES/Apple-Music-Auto-Add` (143.31 GB, 2,396 files)")
    description_parts.append("   - `/Volumes/VIBES/Djay-Pro-Auto-Import` (61.82 GB, 2,410 files)")
    description_parts.append("")
    description_parts.append("2. **Fragmented Playlist Structure**:")
    description_parts.append("   - `/Volumes/VIBES/Playlists/Unassigned` (67.06 GB, 1,380 files)")
    description_parts.append("   - Multiple playlist directories with inconsistent naming")
    description_parts.append("   - Duplicate playlist directories (e.g., 'Good Music' vs 'Good_Music')")
    description_parts.append("")
    description_parts.append("3. **Legacy Music-dep Structure**:")
    description_parts.append("   - `/Volumes/VIBES/Music-dep/` with artist/album subdirectories")
    description_parts.append("   - Inconsistent organization patterns")
    description_parts.append("")
    description_parts.append("4. **Soundcloud Downloads**:")
    description_parts.append("   - `/Volumes/VIBES/Soundcloud Downloads/` with various subdirectories")
    description_parts.append("   - Mixed organization formats")
    description_parts.append("")
    
    description_parts.append("## Target Structure (Per Marketing System Workflows)")
    description_parts.append("")
    description_parts.append("Based on `PRODUCTION_MUSIC_DOWNLOAD_WORKFLOW_COMPREHENSIVE_REPORT.md` and workflow documentation:")
    description_parts.append("")
    description_parts.append("### Expected Directory Structure")
    description_parts.append("")
    description_parts.append("```")
    description_parts.append("/Volumes/VIBES/")
    description_parts.append("├── Playlists/                    # Primary output (OUT_DIR)")
    description_parts.append("│   ├── {playlist_name}/          # Playlist-organized files")
    description_parts.append("│   │   ├── {track_name}.m4a      # M4A/ALAC format (primary)")
    description_parts.append("│   │   └── {track_name}.aiff     # AIFF format (alternate)")
    description_parts.append("│   └── Unassigned/               # Tracks without playlist relation")
    description_parts.append("├── Djay-Pro-Auto-Import/         # BACKUP_DIR (WAV backups)")
    description_parts.append("└── Apple-Music-Auto-Add/         # WAV_BACKUP_DIR")
    description_parts.append("```")
    description_parts.append("")
    description_parts.append("### Key Configuration Values")
    description_parts.append("")
    description_parts.append("- **OUT_DIR**: `/Volumes/VIBES/Playlists` - Playlist-organized output")
    description_parts.append("- **BACKUP_DIR**: `/Volumes/VIBES/Djay-Pro-Auto-Import` - WAV backup location")
    description_parts.append("- **WAV_BACKUP_DIR**: `/Volumes/VIBES/Apple-Music-Auto-Add` - Additional WAV backup")
    description_parts.append("")
    
    description_parts.append("## Required Workflow Phases")
    description_parts.append("")
    description_parts.append("### Phase 1: Comprehensive Indexing")
    description_parts.append("")
    description_parts.append("**Objective:** Create complete catalog of all music files and directories")
    description_parts.append("")
    description_parts.append("**Tasks:**")
    description_parts.append("- [ ] Index all 20,148 music files with metadata")
    description_parts.append("- [ ] Extract audio fingerprints for deduplication")
    description_parts.append("- [ ] Catalog BPM, key, duration for all files")
    description_parts.append("- [ ] Map current directory structure to target structure")
    description_parts.append("- [ ] Identify duplicate files (by fingerprint, hash, filename)")
    description_parts.append("- [ ] Document file metadata (artist, title, album, etc.)")
    description_parts.append("- [ ] Create Notion database entries for all files")
    description_parts.append("")
    
    description_parts.append("### Phase 2: Deduplication Analysis")
    description_parts.append("")
    description_parts.append("**Objective:** Identify and consolidate duplicate files")
    description_parts.append("")
    description_parts.append("**Tasks:**")
    description_parts.append("- [ ] Run fingerprint-based deduplication (using existing `eagle_library_deduplication`)")
    description_parts.append("- [ ] Run hash-based deduplication")
    description_parts.append("- [ ] Run filename-based fuzzy matching")
    description_parts.append("- [ ] Identify 'best' version for each duplicate group (quality, metadata, recency)")
    description_parts.append("- [ ] Generate deduplication report with space recoverable")
    description_parts.append("- [ ] Create backup of duplicates before removal")
    description_parts.append("")
    
    description_parts.append("### Phase 3: Reorganization Planning")
    description_parts.append("")
    description_parts.append("**Objective:** Plan reorganization to match target structure")
    description_parts.append("")
    description_parts.append("**Tasks:**")
    description_parts.append("- [ ] Map current files to target playlist structure")
    description_parts.append("- [ ] Identify playlist associations (from Notion Tracks database)")
    description_parts.append("- [ ] Plan file moves (preserve metadata)")
    description_parts.append("- [ ] Identify files requiring format conversion")
    description_parts.append("- [ ] Plan cleanup of empty/orphaned directories")
    description_parts.append("- [ ] Create reorganization script with dry-run capability")
    description_parts.append("")
    
    description_parts.append("### Phase 4: Execution & Validation")
    description_parts.append("")
    description_parts.append("**Objective:** Execute reorganization with validation")
    description_parts.append("")
    description_parts.append("**Tasks:**")
    description_parts.append("- [ ] Execute dry-run reorganization")
    description_parts.append("- [ ] Validate target structure matches specifications")
    description_parts.append("- [ ] Execute live reorganization with backups")
    description_parts.append("- [ ] Verify file integrity after moves")
    description_parts.append("- [ ] Update Notion database with new paths")
    description_parts.append("- [ ] Update Eagle library with new paths")
    description_parts.append("- [ ] Clean up empty directories")
    description_parts.append("- [ ] Generate final validation report")
    description_parts.append("")
    
    description_parts.append("### Phase 5: Cleanup & Optimization")
    description_parts.append("")
    description_parts.append("**Objective:** Final cleanup and system optimization")
    description_parts.append("")
    description_parts.append("**Tasks:**")
    description_parts.append("- [ ] Remove confirmed duplicate files (after backup)")
    description_parts.append("- [ ] Remove empty directories (834 already identified)")
    description_parts.append("- [ ] Optimize directory structure")
    description_parts.append("- [ ] Update workflow configuration files")
    description_parts.append("- [ ] Document final structure")
    description_parts.append("- [ ] Create maintenance procedures")
    description_parts.append("")
    
    description_parts.append("## Technical Requirements")
    description_parts.append("")
    description_parts.append("### Existing Tools & Workflows")
    description_parts.append("")
    description_parts.append("1. **Production Workflow Script**: `monolithic-scripts/soundcloud_download_prod_merge-2.py`")
    description_parts.append("   - Comprehensive deduplication (Notion + Eagle)")
    description_parts.append("   - Metadata extraction (BPM, key, fingerprint)")
    description_parts.append("   - File organization capabilities")
    description_parts.append("")
    description_parts.append("2. **Eagle Library Deduplication**: `eagle_library_deduplication()` function")
    description_parts.append("   - Fingerprint matching")
    description_parts.append("   - Fuzzy name matching")
    description_parts.append("   - N-gram matching")
    description_parts.append("")
    description_parts.append("3. **Music Workflow Package**: `music_workflow/` module")
    description_parts.append("   - Modular deduplication components")
    description_parts.append("   - Notion integration")
    description_parts.append("   - Eagle integration")
    description_parts.append("")
    
    description_parts.append("### Required New Development")
    description_parts.append("")
    description_parts.append("1. **Volume Scanner & Indexer**")
    description_parts.append("   - Comprehensive file indexing with metadata extraction")
    description_parts.append("   - Directory structure mapping")
    description_parts.append("   - Integration with existing fingerprint tools")
    description_parts.append("")
    description_parts.append("2. **Reorganization Engine**")
    description_parts.append("   - Planned move operations")
    description_parts.append("   - Dry-run execution")
    description_parts.append("   - Validation and rollback capabilities")
    description_parts.append("")
    description_parts.append("3. **Multi-Agent Coordination System**")
    description_parts.append("   - Task breakdown and assignment")
    description_parts.append("   - Progress tracking in Notion")
    description_parts.append("   - Handoff mechanisms between agents")
    description_parts.append("")
    
    description_parts.append("## Multi-Agent Coordination Plan")
    description_parts.append("")
    description_parts.append("### Agent Roles")
    description_parts.append("")
    description_parts.append("1. **Claude Code Agent (Primary)**:")
    description_parts.append("   - Volume scanning and indexing implementation")
    description_parts.append("   - Reorganization script development")
    description_parts.append("   - Integration with existing workflows")
    description_parts.append("")
    description_parts.append("2. **Claude MM1 Agent (Analysis & Coordination)**:")
    description_parts.append("   - Workflow analysis and documentation review")
    description_parts.append("   - Target structure validation")
    description_parts.append("   - Progress monitoring and reporting")
    description_parts.append("")
    description_parts.append("3. **Notion Script Runner (Execution)**:")
    description_parts.append("   - Notion database updates")
    description_parts.append("   - File metadata synchronization")
    description_parts.append("   - Progress tracking in Notion")
    description_parts.append("")
    
    description_parts.append("### Coordination Mechanism")
    description_parts.append("")
    description_parts.append("- Use Agent-Tasks database for task breakdown and assignment")
    description_parts.append("- Use Issues+Questions database (this issue) for overall coordination")
    description_parts.append("- Create sub-tasks for each phase with dependencies")
    description_parts.append("- Regular status updates and handoff documentation")
    description_parts.append("")
    
    description_parts.append("## Acceptance Criteria")
    description_parts.append("")
    description_parts.append("- [ ] All 20,148 music files indexed with complete metadata")
    description_parts.append("- [ ] All duplicates identified and best versions selected")
    description_parts.append("- [ ] All files reorganized to match target structure")
    description_parts.append("- [ ] All files organized by playlist in `/Volumes/VIBES/Playlists/{playlist_name}/`")
    description_parts.append("- [ ] All backups in designated backup directories")
    description_parts.append("- [ ] Empty directories cleaned up")
    description_parts.append("- [ ] Notion database updated with new paths")
    description_parts.append("- [ ] Eagle library updated with new paths")
    description_parts.append("- [ ] Final structure matches marketing system workflow specifications")
    description_parts.append("- [ ] Comprehensive documentation created")
    description_parts.append("")
    
    description_parts.append("## Analysis Report Files")
    description_parts.append("")
    description_parts.append("- **Full Analysis Report**: `logs/vibes_volume_analysis_report.json`")
    description_parts.append("- **Analysis Script**: `analyze_vibes_volume_for_reorganization.py`")
    description_parts.append("")
    
    description_parts.append("## Related Documentation")
    description_parts.append("")
    description_parts.append("- `PRODUCTION_MUSIC_DOWNLOAD_WORKFLOW_COMPREHENSIVE_REPORT.md`")
    description_parts.append("- `MUSIC_WORKFLOW_IMPLEMENTATION_STATUS.md`")
    description_parts.append("- `plans/MUSIC_WORKFLOW_BIFURCATION_STRATEGY.md`")
    description_parts.append("- `unified_config.py` (OUT_DIR, BACKUP_DIR, WAV_BACKUP_DIR configuration)")
    description_parts.append("")
    
    description = "\n".join(description_parts)
    
    return {
        "title": "VIBES Volume Comprehensive Music Reorganization: Indexing, Deduplication & Cleanup",
        "description": description,
        "priority": "High",
        "category": "Music Workflow",
        "status": "Open"
    }

def main():
    """Main execution"""
    print("=" * 80)
    print("CREATE NOTION ISSUE: VIBES VOLUME REORGANIZATION")
    print("=" * 80)
    print()
    
    # Load environment and config
    load_unified_env()
    config = get_unified_config()
    
    # Get Notion client
    notion = get_notion_client()
    
    # Load analysis report
    print("Loading analysis report...")
    try:
        report = load_analysis_report()
        print(f"✓ Loaded analysis report")
        print(f"  Total files: {report['scan_summary']['total_music_files']:,}")
        print(f"  Total size: {report['scan_summary']['total_size_gb']} GB")
    except Exception as e:
        print(f"❌ Error loading analysis report: {e}")
        sys.exit(1)
    
    # Generate issue content
    print("\nGenerating issue content...")
    issue_data = generate_issue_content(report)
    print(f"✓ Generated issue content")
    print(f"  Title: {issue_data['title']}")
    print(f"  Description length: {len(issue_data['description'])} characters")
    
    # Create Notion issue
    print(f"\nCreating Notion issue in Issues+Questions database...")
    print(f"  Database ID: {ISSUES_QUESTIONS_DB_ID}")
    
    try:
        # Create issue with summary description (first 1997 chars)
        summary_desc = issue_data['description'][:1997] + "..." if len(issue_data['description']) > 2000 else issue_data['description']
        
        page_id = create_issue_or_question(
            name=issue_data['title'],
            description=summary_desc,
            priority=issue_data['priority'],
            status="Unreported",  # Use default valid status
            type=["Internal Issue"],
            tags=["reorganization", "deduplication", "multi-agent", "vibes-volume"]
        )
        
        if not page_id:
            raise Exception("Failed to create issue page")
        
        # Add full description as page content blocks
        # Split description into paragraphs and add as blocks
        description_lines = issue_data['description'].split('\n')
        blocks = []
        
        for line in description_lines:
            line = line.strip()
            if not line:
                continue
            
            # Handle markdown headers
            if line.startswith('## '):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": line[3:].strip()}}]
                    }
                })
            elif line.startswith('### '):
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": line[4:].strip()}}]
                    }
                })
            elif line.startswith('- [ ]') or line.startswith('- [x]'):
                # Checkbox list item
                is_checked = line.startswith('- [x]')
                content = line[6:].strip() if is_checked else line[5:].strip()
                blocks.append({
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": content}}],
                        "checked": is_checked
                    }
                })
            elif line.startswith('- ') or line.startswith('  - '):
                # Bullet list item
                content = line.lstrip('- ').strip()
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    }
                })
            elif line.startswith('```'):
                # Code block - skip the fence, we'll handle it differently
                continue
            elif line.startswith('`') and line.endswith('`'):
                # Inline code
                content = line.strip('`')
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {"type": "text", "text": {"content": content}, "annotations": {"code": True}}
                        ]
                    }
                })
            else:
                # Regular paragraph
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": line}}]
                    }
                })
        
        # Add blocks to the page (in chunks of 100, Notion API limit)
        if blocks:
            chunk_size = 100
            for i in range(0, len(blocks), chunk_size):
                chunk = blocks[i:i+chunk_size]
                notion.blocks.children.append(block_id=page_id, children=chunk)
        
        print(f"\n✓ Issue created successfully!")
        print(f"  Page ID: {page_id}")
        print(f"  Notion URL: https://www.notion.so/{page_id.replace('-', '')}")
        print()
        print("=" * 80)
        print("ISSUE CREATION COMPLETE")
        print("=" * 80)
        print()
        print("Next steps:")
        print("1. Review the issue in Notion")
        print("2. Break down into sub-tasks in Agent-Tasks database")
        print("3. Assign tasks to appropriate agents")
        print("4. Begin Phase 1: Comprehensive Indexing")
        
    except Exception as e:
        print(f"\n❌ Error creating Notion issue: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
