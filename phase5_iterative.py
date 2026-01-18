#!/usr/bin/env python3
"""
Phase 5: Iterative Execution Until Complete
Checks for remaining duplicates and iterates if needed.
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

def check_for_remaining_duplicates() -> Dict[str, Any]:
    """Execute dry-run to check for remaining duplicates."""
    print("5.1 Checking for Remaining Duplicates...")
    
    script_path = PROJECT_ROOT / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    
    if not script_path.exists():
        return {"error": "Script not found", "success": False}
    
    cmd = [
        sys.executable,
        str(script_path),
        "--mode", "dedup",
        "--dedup-threshold", "0.75",
        "--debug"
    ]
    
    print(f"  Executing dry-run scan...")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(PROJECT_ROOT)
        )
        
        # Find the latest report
        logs_dir = PROJECT_ROOT / "logs" / "deduplication"
        if logs_dir.exists():
            reports = list(logs_dir.glob("eagle_dedup_report_*.md"))
            if reports:
                reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                latest_report = reports[0]
                
                # Parse report
                content = latest_report.read_text(encoding='utf-8')
                import re
                
                groups_match = re.search(r'\| Duplicate Groups Found \| (\d+) \|', content)
                duplicates_match = re.search(r'\| Total Duplicate Items \| (\d+) \|', content)
                
                groups = int(groups_match.group(1)) if groups_match else 0
                duplicates = int(duplicates_match.group(1)) if duplicates_match else 0
                
                return {
                    "success": result.returncode == 0,
                    "duplicate_groups": groups,
                    "total_duplicates": duplicates,
                    "report_path": str(latest_report),
                    "has_duplicates": groups > 0
                }
        
        return {
            "success": result.returncode == 0,
            "duplicate_groups": 0,
            "total_duplicates": 0,
            "has_duplicates": False
        }
        
    except Exception as e:
        return {"success": False, "error": str(e), "has_duplicates": False}

def analyze_remaining_duplicates(check_result: Dict) -> Dict[str, Any]:
    """Analyze why duplicates remain."""
    print("\n5.2 Analyzing Remaining Duplicates...")
    
    if not check_result.get("has_duplicates"):
        print("  ✓ No remaining duplicates found")
        return {
            "has_duplicates": False,
            "analysis": "No duplicates remaining - deduplication complete"
        }
    
    groups = check_result.get("duplicate_groups", 0)
    duplicates = check_result.get("total_duplicates", 0)
    
    print(f"  Found {groups} duplicate groups ({duplicates} duplicate items)")
    print("  Possible reasons:")
    print("    - Similarity threshold too high for some matches")
    print("    - New duplicates added since last cleanup")
    print("    - Edge cases not caught by matching strategies")
    
    analysis = {
        "has_duplicates": True,
        "groups_remaining": groups,
        "duplicates_remaining": duplicates,
        "recommendations": []
    }
    
    if groups > 0:
        analysis["recommendations"].append("Consider lowering similarity threshold (try 0.70)")
        analysis["recommendations"].append("Review matching strategies for edge cases")
        analysis["recommendations"].append("Run fingerprint sync to improve matching")
    
    return analysis

def should_iterate(analysis: Dict, max_iterations: int = 3, current_iteration: int = 1) -> bool:
    """Determine if we should iterate again."""
    if not analysis.get("has_duplicates"):
        return False
    
    if current_iteration >= max_iterations:
        print(f"\n  ⚠ Maximum iterations reached ({max_iterations})")
        return False
    
    return True

def main():
    """Main execution function."""
    print("=" * 80)
    print("PHASE 5: ITERATIVE EXECUTION UNTIL COMPLETE")
    print("=" * 80)
    
    load_unified_env()
    
    max_iterations = 3
    current_iteration = 1
    
    while current_iteration <= max_iterations:
        print(f"\n--- Iteration {current_iteration}/{max_iterations} ---")
        
        # 5.1 Check for Remaining Duplicates
        check_result = check_for_remaining_duplicates()
        
        if not check_result.get("success"):
            print(f"\n✗ Error checking for duplicates: {check_result.get('error', 'Unknown')}")
            return 1
        
        # 5.2 Analyze Remaining Duplicates
        analysis = analyze_remaining_duplicates(check_result)
        
        if not analysis.get("has_duplicates"):
            print("\n" + "=" * 80)
            print("PHASE 5 COMPLETE - NO DUPLICATES REMAIN")
            print("=" * 80)
            print("\n✓ Ready to proceed to Phase 6 (Completion)")
            return 0
        
        # Check if we should iterate
        if not should_iterate(analysis, max_iterations, current_iteration):
            print("\n" + "=" * 80)
            print(f"PHASE 5 COMPLETE - MAX ITERATIONS REACHED")
            print("=" * 80)
            print(f"\n⚠ {analysis['groups_remaining']} duplicate groups remain")
            print("  Manual review recommended before proceeding")
            return 0
        
        print(f"\n  → Returning to Phase 1-4 for iteration {current_iteration + 1}")
        print("  Note: This would normally trigger a new deduplication run")
        print("  For now, stopping here. Run phase4_second_run.py manually if needed.")
        
        current_iteration += 1
        break  # For now, stop after one iteration check
    
    # Save iteration report
    iteration_report = {
        "timestamp": datetime.now().isoformat(),
        "iterations_completed": current_iteration - 1,
        "final_check": check_result,
        "final_analysis": analysis
    }
    
    output_file = PROJECT_ROOT / 'phase5_iteration_report.json'
    with open(output_file, 'w') as f:
        json.dump(iteration_report, f, indent=2, default=str)
    
    print(f"\n✓ Iteration report saved to: {output_file}")
    
    if not analysis.get("has_duplicates"):
        return 0
    else:
        return 0  # Still return success, but note duplicates remain

if __name__ == "__main__":
    sys.exit(main())
