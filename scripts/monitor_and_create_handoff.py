#!/usr/bin/env python3
"""
Monitor batch fingerprint embedding script completion and create comprehensive audit report
and handoff files for Claude Code Agent.
"""

import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_fingerprint_audit_report import parse_batch_log, generate_audit_report

def wait_for_completion(max_wait_minutes=120):
    """Wait for batch fingerprint embedding script to complete."""
    log_file = "/tmp/batch_fingerprint_embedding.log"
    check_interval = 30  # Check every 30 seconds
    max_checks = (max_wait_minutes * 60) // check_interval
    
    print(f"Monitoring batch fingerprint embedding script...")
    print(f"Log file: {log_file}")
    print(f"Max wait time: {max_wait_minutes} minutes")
    print()
    
    for i in range(max_checks):
        # Check if process is still running
        result = subprocess.run(
            ["pgrep", "-f", "batch_fingerprint_embedding.py"],
            capture_output=True
        )
        
        if result.returncode != 0:
            print("✅ Script has completed!")
            time.sleep(5)  # Wait a bit more for final log writes
            return True
        
        # Show progress
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                # Find last progress line
                for line in reversed(lines):
                    if "[INFO] [" in line and "/1000] Processing" in line:
                        print(f"⏳ Still running... {line.strip()}")
                        break
        except:
            pass
        
        time.sleep(check_interval)
    
    print("⚠️  Max wait time exceeded. Proceeding with current log state.")
    return False

def create_notion_task_and_handoff(audit_report_path: Path):
    """Create Notion Agent-Tasks item and handoff trigger file."""
    
    # Read audit report
    with open(audit_report_path, 'r') as f:
        report_content = f.read()
    
    # Parse stats from report
    stats = parse_batch_log("/tmp/batch_fingerprint_embedding.log")
    
    # Create handoff trigger file for Claude Code Agent
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trigger_dir = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers/Claude-Code-Agent/01_inbox")
    trigger_dir.mkdir(parents=True, exist_ok=True)
    
    trigger_file = trigger_dir / f"{timestamp}__HANDOFF__Review-Fingerprint-Batch-Embedding-Audit-Report__fingerprint_audit.json"
    
    handoff_content = {
        "task_id": "TO_BE_CREATED",
        "task_title": "Review Fingerprint Batch Embedding Audit Report and Continue Remediation",
        "task_url": "",
        "project_id": "2e5e7361-6c27-819d-91fc-dc2707c7b36a",
        "project_title": "Complete Fingerprint System Implementation Across Eagle Library Workflows",
        "description": f"""## Objective

Review the comprehensive audit and performance report for batch fingerprint embedding execution and continue with remediation or implementation work as needed.

## Context

Batch fingerprint embedding script was executed to embed fingerprints in existing Eagle library audio files. This task requires review of the execution results, identification of issues, and continuation of remediation work.

## Audit Report

A comprehensive audit report has been generated documenting:
- Execution metrics and performance
- Success/failure rates
- Issues encountered
- Recommendations for next steps

**Report Location:** {audit_report_path}

## Execution Summary

- **Files Processed:** {stats['processed']}
- **Successfully Embedded:** {stats['succeeded']}
- **Failed:** {stats['failed']}
- **Success Rate:** {(stats['succeeded'] / stats['processed'] * 100) if stats['processed'] > 0 else 0:.2f}%
- **WAV Files Skipped:** {stats['wav_skipped']}
- **Eagle Tags Synced:** {stats['eagle_synced']}

## Known Issues

1. **Eagle Client Sync Error:** urllib import issue (FIXED in code, but running process didn't pick up fix)
2. **WAV File Limitations:** {stats['wav_skipped']} WAV files cannot have fingerprints embedded

## Required Actions

1. **Review Audit Report:** Read and analyze the comprehensive audit report
2. **Verify Results:** Check that fingerprints were successfully embedded
3. **Address Issues:** Fix any remaining issues identified in the report
4. **Continue Processing:** If needed, continue batch processing with remaining files
5. **Update Notion:** Update Agent-Tasks with review results and next steps
6. **Create Next Handoff:** Create handoff for next phase of work

## Success Criteria

- [ ] Audit report reviewed and understood
- [ ] All issues identified and documented
- [ ] Remediation plan created for remaining issues
- [ ] Notion tasks updated with results
- [ ] Next handoff created if needed

## Files and Artifacts

- **Audit Report:** {audit_report_path}
- **Log File:** /tmp/batch_fingerprint_embedding.log
- **Script:** scripts/batch_fingerprint_embedding.py

## Next Steps

After review, determine:
1. Whether to continue batch processing with remaining files
2. What remediation is needed for identified issues
3. Whether fingerprint coverage verification is needed
4. What the next phase of work should be
""",
        "status": "Ready",
        "agent_name": "Claude Code Agent",
        "agent_type": "MM1",
        "handoff_instructions": "Review the comprehensive audit report, analyze execution results, identify issues, and continue with remediation or implementation work. Update Notion tasks and create next handoff as needed.",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "priority": "High"
    }
    
    with open(trigger_file, 'w') as f:
        json.dump(handoff_content, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Created handoff trigger file: {trigger_file}")
    return trigger_file, handoff_content

def main():
    """Main execution."""
    print("=" * 80)
    print("Batch Fingerprint Embedding - Completion Monitor and Handoff Creator")
    print("=" * 80)
    print()
    
    # Wait for script completion
    completed = wait_for_completion(max_wait_minutes=120)
    
    # Generate audit report
    print()
    print("Generating audit report...")
    stats = parse_batch_log("/tmp/batch_fingerprint_embedding.log")
    report = generate_audit_report(stats, "/tmp/batch_fingerprint_embedding.log")
    
    report_file = PROJECT_ROOT / "FINGERPRINT_BATCH_EMBEDDING_AUDIT_REPORT.md"
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"✅ Audit report generated: {report_file}")
    print()
    
    # Create Notion task and handoff
    print("Creating Notion task and handoff files...")
    trigger_file, handoff_content = create_notion_task_and_handoff(report_file)
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Files Processed: {stats['processed']}")
    print(f"Successfully Embedded: {stats['succeeded']}")
    print(f"Failed: {stats['failed']}")
    print(f"Success Rate: {(stats['succeeded'] / stats['processed'] * 100) if stats['processed'] > 0 else 0:.2f}%")
    print()
    print(f"✅ Audit Report: {report_file}")
    print(f"✅ Handoff Trigger: {trigger_file}")
    print()
    print("Next: Create Notion Agent-Tasks item using main.py or Notion API")
    print("=" * 80)

if __name__ == "__main__":
    main()
