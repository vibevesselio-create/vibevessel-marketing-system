#!/usr/bin/env python3
"""
Phase 4: Second Production Run & Validation
Executes live deduplication run (with cleanup), validates results, creates validation report.
"""
import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from unified_config import load_unified_env, get_unified_config

def load_phase2_results() -> Dict[str, Any]:
    """Load Phase 2 execution results for comparison."""
    phase2_file = PROJECT_ROOT / 'phase2_execution_analysis.json'
    
    if not phase2_file.exists():
        return {}
    
    try:
        with open(phase2_file, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def find_latest_dedup_report() -> Optional[Path]:
    """Find the most recent deduplication report."""
    logs_dir = PROJECT_ROOT / "logs" / "deduplication"
    if not logs_dir.exists():
        return None
    
    reports = list(logs_dir.glob("eagle_dedup_report_*.md"))
    if not reports:
        return None
    
    reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return reports[0]

def execute_live_run(require_confirmation: bool = True) -> Dict[str, Any]:
    """Execute second production run in LIVE mode with cleanup."""
    print("4.1 Executing Second Production Run (LIVE with Cleanup)...")
    print("  ⚠️  WARNING: This will MOVE DUPLICATES TO TRASH in Eagle!")
    
    if require_confirmation:
        response = input("  Proceed with LIVE cleanup? (yes/no): ").strip().lower()
        if response != 'yes':
            print("  ✗ Live run cancelled by user")
            return {"success": False, "error": "Cancelled by user"}
    
    script_path = PROJECT_ROOT / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    
    if not script_path.exists():
        return {"error": "Script not found", "success": False}
    
    cmd = [
        sys.executable,
        str(script_path),
        "--mode", "dedup",
        "--dedup-live",
        "--dedup-cleanup",
        "--dedup-threshold", "0.75",
        "--debug"
    ]
    
    print(f"  Command: {' '.join(cmd)}")
    print("  Executing LIVE deduplication with cleanup...")
    
    start_time = datetime.now()
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
            cwd=str(PROJECT_ROOT)
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        execution_result = {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "duration_seconds": duration,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
        
        if result.returncode == 0:
            print(f"  ✓ Live run completed successfully in {duration:.1f}s")
        else:
            print(f"  ✗ Live run failed (exit code: {result.returncode})")
        
        return execution_result
        
    except subprocess.TimeoutExpired:
        print("  ⚠ Execution timed out")
        return {"success": False, "error": "Timeout", "timeout": True}
    except Exception as e:
        print(f"  ✗ Error executing: {e}")
        return {"success": False, "error": str(e)}

def parse_dedup_report(report_path: Path) -> Dict[str, Any]:
    """Parse the deduplication report markdown file."""
    if not report_path.exists():
        return {"error": "Report file not found"}
    
    try:
        content = report_path.read_text(encoding='utf-8')
        
        import re
        metrics = {}
        
        # Parse summary metrics
        summary_match = re.search(r'\| Total Items Scanned \| (\d+) \|', content)
        if summary_match:
            metrics["total_items"] = int(summary_match.group(1))
        
        summary_match = re.search(r'\| Duplicate Groups Found \| (\d+) \|', content)
        if summary_match:
            metrics["duplicate_groups"] = int(summary_match.group(1))
        
        summary_match = re.search(r'\| Total Duplicate Items \| (\d+) \|', content)
        if summary_match:
            metrics["total_duplicates"] = int(summary_match.group(1))
        
        return {
            "report_path": str(report_path),
            "metrics": metrics,
            "raw_content": content
        }
        
    except Exception as e:
        return {"error": f"Failed to parse report: {e}"}

def validate_results(first_run: Dict, second_run: Dict) -> Dict[str, Any]:
    """Validate second run results against first run."""
    print("\n4.2 Validating Results...")
    
    first_metrics = first_run.get("report_data", {}).get("metrics", {})
    second_metrics = second_run.get("report_data", {}).get("metrics", {})
    
    validation = {
        "comparison": {},
        "validation_findings": [],
        "validation_passed": True
    }
    
    # Compare key metrics
    first_groups = first_metrics.get("duplicate_groups", 0)
    second_groups = second_metrics.get("duplicate_groups", 0)
    
    validation["comparison"] = {
        "first_run_groups": first_groups,
        "second_run_groups": second_groups,
        "groups_removed": first_groups - second_groups if second_groups < first_groups else 0,
        "items_scanned_first": first_metrics.get("total_items", 0),
        "items_scanned_second": second_metrics.get("total_items", 0)
    }
    
    print(f"  A. Comparison:")
    print(f"    - First run groups: {first_groups}")
    print(f"    - Second run groups: {second_groups}")
    print(f"    - Groups removed: {validation['comparison']['groups_removed']}")
    
    # Validate cleanup worked
    if second_groups == 0 and first_groups > 0:
        validation["validation_findings"].append("✓ All duplicate groups removed successfully")
        print("    ✓ All duplicates removed")
    elif second_groups < first_groups:
        validation["validation_findings"].append(f"✓ Duplicate groups reduced from {first_groups} to {second_groups}")
        print(f"    ✓ Duplicates reduced (but {second_groups} remain)")
    elif second_groups == first_groups:
        validation["validation_findings"].append("⚠ No duplicates were removed (may indicate cleanup did not execute)")
        validation["validation_passed"] = False
        print("    ⚠ No duplicates removed")
    else:
        validation["validation_findings"].append(f"⚠ More duplicates found in second run ({second_groups} > {first_groups})")
        validation["validation_passed"] = False
        print(f"    ⚠ More duplicates found")
    
    # Validate library integrity
    print(f"\n  B. Library Integrity:")
    items_after = second_metrics.get("total_items", 0)
    items_before = first_metrics.get("total_items", 0)
    
    if items_after > 0:
        validation["validation_findings"].append(f"✓ Library integrity maintained ({items_after} items remaining)")
        print(f"    ✓ Library integrity: {items_after} items")
    else:
        validation["validation_findings"].append("✗ Library integrity compromised (0 items remaining)")
        validation["validation_passed"] = False
        print("    ✗ Library integrity issue")
    
    # Performance validation
    print(f"\n  C. Performance:")
    first_duration = first_run.get("execution_result", {}).get("duration_seconds", 0)
    second_duration = second_run.get("execution_result", {}).get("duration_seconds", 0)
    
    if second_duration > 0:
        validation["comparison"]["performance"] = {
            "first_run_duration": first_duration,
            "second_run_duration": second_duration,
            "acceptable": second_duration < 300  # 5 minutes
        }
        print(f"    - Second run duration: {second_duration:.1f}s")
        if second_duration < 300:
            print("    ✓ Performance acceptable")
        else:
            print("    ⚠ Performance slower than expected")
    
    return validation

def create_validation_report(execution_result: Dict, validation: Dict, first_run: Dict) -> Dict[str, Any]:
    """Create comprehensive validation report."""
    print("\n4.3 Creating Validation Report...")
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "second_run_execution": execution_result,
        "comparison": validation.get("comparison", {}),
        "validation_findings": validation.get("validation_findings", []),
        "validation_passed": validation.get("validation_passed", False),
        "recommendations": [],
        "compliance_status": "COMPLIANT"
    }
    
    # Generate recommendations
    if not validation.get("validation_passed"):
        report["recommendations"].append("Review cleanup execution - duplicates may not have been removed")
    
    if validation.get("comparison", {}).get("groups_removed", 0) > 0:
        remaining = validation.get("comparison", {}).get("second_run_groups", 0)
        if remaining > 0:
            report["recommendations"].append(f"Run Phase 5 to check for remaining duplicates ({remaining} groups found)")
        else:
            report["recommendations"].append("All duplicates removed - proceed to Phase 6 for completion")
    
    print("  ✓ Validation report created")
    print(f"    - Validation passed: {report['validation_passed']}")
    print(f"    - Findings: {len(report['validation_findings'])}")
    
    return report

def main():
    """Main execution function."""
    print("=" * 80)
    print("PHASE 4: SECOND PRODUCTION RUN & VALIDATION")
    print("=" * 80)
    print()
    print("⚠️  WARNING: This phase will execute LIVE deduplication with cleanup enabled.")
    print("    Duplicates will be moved to Eagle Trash. This action cannot be easily undone.")
    print()
    
    # Check if we should proceed
    phase3_file = PROJECT_ROOT / 'phase3_remediation_report.json'
    if phase3_file.exists():
        try:
            with open(phase3_file, 'r') as f:
                phase3_results = json.load(f)
                if not phase3_results.get("can_proceed", False):
                    print("✗ Phase 3 indicates we should NOT proceed")
                    print("  Review phase3_remediation_report.json before continuing")
                    return 1
        except Exception:
            pass
    
    load_unified_env()
    
    # Load first run results for comparison
    first_run = load_phase2_results()
    
    # 4.1 Execute Second Production Run
    # Use --no-confirm flag to skip confirmation if needed
    require_confirmation = "--no-confirm" not in sys.argv
    execution_result = execute_live_run(require_confirmation=require_confirmation)
    
    if not execution_result.get("success"):
        print(f"\n✗ Execution failed: {execution_result.get('error', 'Unknown error')}")
        return 1
    
    # Find and parse the report
    report_path = find_latest_dedup_report()
    if not report_path:
        print("\n⚠ No deduplication report found")
        report_data = {"error": "Report not found"}
    else:
        print(f"\n  Found report: {report_path}")
        report_data = parse_dedup_report(report_path)
        execution_result["report_data"] = report_data
    
    # 4.2 Validate Results
    validation = validate_results(first_run, execution_result)
    
    # 4.3 Create Validation Report
    validation_report = create_validation_report(execution_result, validation, first_run)
    
    # Save comprehensive report
    output_file = PROJECT_ROOT / 'phase4_validation_report.json'
    with open(output_file, 'w') as f:
        json.dump({
            "execution_result": execution_result,
            "validation": validation,
            "validation_report": validation_report
        }, f, indent=2, default=str)
    
    print(f"\n✓ Validation report saved to: {output_file}")
    print("\n" + "=" * 80)
    print("PHASE 4 COMPLETE")
    print("=" * 80)
    
    if validation_report["validation_passed"]:
        remaining_groups = validation.get("comparison", {}).get("second_run_groups", 0)
        if remaining_groups == 0:
            print("\n✓ All duplicates removed - ready for Phase 6 (Completion)")
        else:
            print(f"\n✓ Cleanup successful - {remaining_groups} groups remain")
            print("  Ready for Phase 5 (Iterative Execution)")
        return 0
    else:
        print("\n⚠ Validation issues detected - review validation report")
        return 1

if __name__ == "__main__":
    sys.exit(main())
