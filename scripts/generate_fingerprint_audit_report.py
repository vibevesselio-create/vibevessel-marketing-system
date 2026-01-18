#!/usr/bin/env python3
"""
Generate Comprehensive Audit and Performance Report for Batch Fingerprint Embedding
"""

import re
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any

def parse_batch_log(log_file: str) -> Dict[str, Any]:
    """Parse batch fingerprint embedding log file."""
    stats = {
        "total_scanned": 0,
        "already_has_fingerprint": 0,
        "planned": 0,
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "eagle_synced": 0,
        "notion_updated": 0,
        "wav_skipped": 0,
        "errors": [],
        "start_time": None,
        "end_time": None,
        "duration_seconds": None
    }
    
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
            
        # Extract summary statistics
        for i, line in enumerate(lines):
            # Find summary section
            if "BATCH FINGERPRINT EMBEDDING SUMMARY" in line:
                # Parse next few lines for stats
                for j in range(i, min(i+20, len(lines))):
                    summary_line = lines[j]
                    if "Total files scanned:" in summary_line:
                        match = re.search(r'Total files scanned: (\d+)', summary_line)
                        if match:
                            stats["total_scanned"] = int(match.group(1))
                    elif "Already have fingerprints:" in summary_line:
                        match = re.search(r'Already have fingerprints: (\d+)', summary_line)
                        if match:
                            stats["already_has_fingerprint"] = int(match.group(1))
                    elif "Files planned:" in summary_line:
                        match = re.search(r'Files planned: (\d+)', summary_line)
                        if match:
                            stats["planned"] = int(match.group(1))
                    elif "Files processed:" in summary_line:
                        match = re.search(r'Files processed: (\d+)', summary_line)
                        if match:
                            stats["processed"] = int(match.group(1))
                    elif "Successfully embedded:" in summary_line:
                        match = re.search(r'Successfully embedded: (\d+)', summary_line)
                        if match:
                            stats["succeeded"] = int(match.group(1))
                    elif "Failed:" in summary_line:
                        match = re.search(r'Failed: (\d+)', summary_line)
                        if match:
                            stats["failed"] = int(match.group(1))
                    elif "Eagle tags synced:" in summary_line:
                        match = re.search(r'Eagle tags synced: (\d+)', summary_line)
                        if match:
                            stats["eagle_synced"] = int(match.group(1))
                    elif "Notion tracks updated:" in summary_line:
                        match = re.search(r'Notion tracks updated: (\d+)', summary_line)
                        if match:
                            stats["notion_updated"] = int(match.group(1))
            
            # Count WAV files skipped
            if "WAV files have limited metadata support" in line:
                stats["wav_skipped"] += 1
            
            # Count errors
            if "ERROR" in line or "❌" in line:
                stats["errors"].append(line.strip())
            
            # Extract timestamps
            timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if timestamp_match:
                if not stats["start_time"]:
                    stats["start_time"] = timestamp_match.group(1)
                stats["end_time"] = timestamp_match.group(1)
    
    except FileNotFoundError:
        print(f"Log file not found: {log_file}")
    except Exception as e:
        print(f"Error parsing log: {e}")
    
    # Calculate duration if we have both times
    if stats["start_time"] and stats["end_time"]:
        try:
            start = datetime.strptime(stats["start_time"], "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(stats["end_time"], "%Y-%m-%d %H:%M:%S")
            stats["duration_seconds"] = (end - start).total_seconds()
        except:
            pass
    
    return stats

def generate_audit_report(stats: Dict[str, Any], log_file: str) -> str:
    """Generate comprehensive audit and performance report."""
    
    report = f"""# Batch Fingerprint Embedding - Comprehensive Audit and Performance Report

**Generated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}

## Executive Summary

This report documents the execution, performance, and outcomes of the batch fingerprint embedding process for the Eagle library audio files.

### Key Metrics

- **Total Files Scanned:** {stats['total_scanned']:,}
- **Files Already Having Fingerprints:** {stats['already_has_fingerprint']:,}
- **Files Planned for Processing:** {stats['planned']:,}
- **Files Processed:** {stats['processed']:,}
- **Successfully Embedded:** {stats['succeeded']:,}
- **Failed:** {stats['failed']:,}
- **WAV Files Skipped (No Metadata Support):** {stats['wav_skipped']:,}
- **Eagle Tags Synced:** {stats['eagle_synced']:,}
- **Notion Tracks Updated:** {stats['notion_updated']:,}

### Performance Metrics

- **Start Time:** {stats['start_time'] or 'N/A'}
- **End Time:** {stats['end_time'] or 'N/A'}
- **Duration:** {stats['duration_seconds'] / 60 if stats['duration_seconds'] else 0:.2f} minutes ({stats['duration_seconds'] or 0:.2f} seconds)
- **Success Rate:** {(stats['succeeded'] / stats['processed'] * 100) if stats['processed'] > 0 else 0:.2f}%
- **Processing Rate:** {(stats['processed'] / (stats['duration_seconds'] / 60)) if stats['duration_seconds'] and stats['duration_seconds'] > 0 else 0:.2f} files/minute

## Detailed Analysis

### File Processing Breakdown

1. **Files Scanned:** {stats['total_scanned']:,} total audio files found in scanned directories
2. **Pre-existing Fingerprints:** {stats['already_has_fingerprint']:,} files already had fingerprints embedded
3. **New Fingerprints Embedded:** {stats['succeeded']:,} files successfully processed
4. **Failures:** {stats['failed']:,} files failed during processing

### Format Support

- **WAV Files:** {stats['wav_skipped']:,} WAV files were skipped due to limited metadata support
- **Supported Formats:** M4A, MP3, FLAC, AIFF files were processed

### Integration Status

- **Eagle Tag Sync:** {stats['eagle_synced']:,} fingerprints synced to Eagle library tags
- **Notion Updates:** {stats['notion_updated']:,} Notion track records updated

## Issues and Errors

### Known Issues

1. **Eagle Client Sync Error:** 
   - Error: "cannot access local variable 'urllib' where it is not associated with a value"
   - Impact: Eagle tag syncing failed for some files, falling back to direct API
   - Status: Fixed in code (urllib.parse import added), but running process didn't pick up fix
   - Resolution: Fix applied to `music_workflow/integrations/eagle/client.py`

2. **WAV File Limitations:**
   - WAV files cannot have fingerprints embedded in metadata
   - Impact: {stats['wav_skipped']:,} files skipped
   - Recommendation: Consider converting WAV files to M4A/FLAC for fingerprint support

### Error Count

- **Total Errors Encountered:** {len(stats['errors'])}
- **Critical Errors:** {len([e for e in stats['errors'] if 'CRITICAL' in e or 'FATAL' in e])}
- **Warnings:** {len([e for e in stats['errors'] if 'WARNING' in e or '⚠️' in e])}

## Recommendations

### Immediate Actions

1. **Fix Eagle Client Sync:** The urllib import issue has been fixed. Restart batch processing to enable full Eagle tag syncing.

2. **Continue Batch Processing:** Process remaining files with increased limits:
   ```bash
   python3 batch_fingerprint_embedding.py --execute --limit 5000 --verbose
   ```

3. **Verify Fingerprint Coverage:** Run fingerprint sync to verify coverage:
   ```bash
   python3 run_fingerprint_dedup_production.py --execute --sync-only
   ```

### Long-term Improvements

1. **WAV File Handling:** Develop strategy for WAV files (conversion or alternative fingerprint storage)

2. **Performance Optimization:** 
   - Current rate: {(stats['processed'] / (stats['duration_seconds'] / 60)) if stats['duration_seconds'] and stats['duration_seconds'] > 0 else 0:.2f} files/minute
   - Consider parallel processing for large batches

3. **Error Handling:** Improve error recovery and retry logic for failed files

## Next Steps

1. **Validation:** Run fingerprint coverage check to verify embedded fingerprints
2. **Deduplication Test:** Test deduplication with fingerprint-based matching
3. **Documentation:** Update Notion tasks with execution results
4. **Remediation:** Address any remaining issues identified in this report

## Log File Location

- **Log File:** {log_file}
- **Report Generated:** {datetime.now(timezone.utc).isoformat()}

---

**Report Generated By:** Batch Fingerprint Embedding Audit Script
**For:** Fingerprint System Implementation Project
"""
    
    return report

if __name__ == "__main__":
    log_file = "/tmp/batch_fingerprint_embedding.log"
    stats = parse_batch_log(log_file)
    report = generate_audit_report(stats, log_file)
    
    # Save report
    report_file = Path(__file__).parent.parent / "FINGERPRINT_BATCH_EMBEDDING_AUDIT_REPORT.md"
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"Audit report generated: {report_file}")
    print(f"\nSummary:")
    print(f"  Processed: {stats['processed']}")
    print(f"  Succeeded: {stats['succeeded']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Success Rate: {(stats['succeeded'] / stats['processed'] * 100) if stats['processed'] > 0 else 0:.2f}%")
