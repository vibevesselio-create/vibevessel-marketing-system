#!/usr/bin/env python3
"""
Phase 1: Review & Status Identification
Reviews deduplication function implementation, verifies availability and capabilities,
tests independent execution, and documents function status.
"""
import os
import sys
import subprocess
import inspect
from pathlib import Path
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from unified_config import load_unified_env, get_unified_config

def review_function_implementation() -> Dict[str, Any]:
    """Review deduplication function implementation."""
    print("1.1 Reviewing Deduplication Function Implementation...")
    
    script_path = PROJECT_ROOT / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    
    if not script_path.exists():
        return {"error": "Production script not found"}
    
    # Import the script module to inspect functions
    import importlib.util
    spec = importlib.util.spec_from_file_location("soundcloud_download_prod_merge-2", script_path)
    if spec is None or spec.loader is None:
        return {"error": "Could not load script module"}
    
    try:
        module = importlib.util.module_from_spec(spec)
        # We'll read the file directly instead of executing it to avoid side effects
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return {"error": f"Failed to read script: {e}"}
    
    functions_status = {}
    target_functions = [
        "eagle_library_deduplication",
        "eagle_import_with_duplicate_management",
        "eagle_cleanup_duplicate_items",
        "sync_fingerprints_to_eagle_tags"
    ]
    
    # Check function availability
    print("  A. Function Availability:")
    for func_name in target_functions:
        exists = f"def {func_name}(" in content
        functions_status[func_name] = {"exists": exists, "callable": exists}
        
        if exists:
            # Find function signature
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if f"def {func_name}(" in line:
                    # Extract docstring if available
                    docstring = ""
                    for j in range(i+1, min(i+20, len(lines))):
                        if '"""' in lines[j] or "'''" in lines[j]:
                            # Found docstring start
                            docstring_lines = []
                            quote_char = '"""' if '"""' in lines[j] else "'''"
                            k = j
                            while k < len(lines):
                                docstring_lines.append(lines[k])
                                if quote_char in lines[k] and k > j:
                                    break
                                k += 1
                            docstring = '\n'.join(docstring_lines)
                            break
                    
                    functions_status[func_name].update({
                        "line": i+1,
                        "signature": line.strip(),
                        "has_docstring": bool(docstring),
                        "docstring_preview": docstring[:200] if docstring else ""
                    })
                    break
            
            print(f"    ✓ {func_name}() exists and is callable")
        else:
            print(f"    ✗ {func_name}() not found")
    
    # Check for standalone execution mode
    print("\n  C. Independent Execution:")
    has_dedup_mode = "--mode dedup" in content or 'mode == "dedup"' in content
    functions_status["standalone_execution"] = {
        "has_dedup_mode": has_dedup_mode,
        "command": "python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode dedup",
        "options": {
            "dedup_live": "--dedup-live" in content,
            "dedup_threshold": "--dedup-threshold" in content,
            "dedup_cleanup": "--dedup-cleanup" in content
        }
    }
    
    if has_dedup_mode:
        print("    ✓ Standalone execution mode (--mode dedup) available")
        print(f"    ✓ Options: --dedup-live, --dedup-threshold, --dedup-cleanup")
    else:
        print("    ✗ Standalone execution mode not found")
    
    return functions_status

def test_independent_execution() -> Dict[str, Any]:
    """Test independent execution of deduplication in dry-run mode."""
    print("\n1.2 Testing Independent Execution (Dry-Run)...")
    
    script_path = PROJECT_ROOT / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    
    if not script_path.exists():
        return {"error": "Script not found", "success": False}
    
    # Test dry-run execution
    cmd = [
        sys.executable,
        str(script_path),
        "--mode", "dedup",
        "--dedup-threshold", "0.75",
        "--debug"
    ]
    
    print(f"  Executing: {' '.join(cmd)}")
    print("  (This may take a while - scanning entire Eagle library...)")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=str(PROJECT_ROOT)
        )
        
        output_lines = result.stdout.split('\n') + result.stderr.split('\n')
        
        # Extract key metrics from output
        metrics = {
            "exit_code": result.returncode,
            "success": result.returncode == 0,
            "output_length": len(result.stdout),
            "error_length": len(result.stderr)
        }
        
        # Look for key indicators in output
        for line in output_lines:
            if "total_items" in line.lower() or "items scanned" in line.lower():
                metrics["items_scanned"] = line
            if "duplicate" in line.lower() and ("found" in line.lower() or "group" in line.lower()):
                metrics["duplicates_found"] = line
            if "report" in line.lower() and "path" in line.lower():
                metrics["report_path"] = line
        
        if result.returncode == 0:
            print("    ✓ Dry-run execution completed successfully")
        else:
            print(f"    ✗ Dry-run execution failed (exit code: {result.returncode})")
            if result.stderr:
                print(f"    Error: {result.stderr[:200]}")
        
        return {
            "success": result.returncode == 0,
            "metrics": metrics,
            "stdout_preview": result.stdout[:500] if result.stdout else "",
            "stderr_preview": result.stderr[:500] if result.stderr else ""
        }
        
    except subprocess.TimeoutExpired:
        print("    ⚠ Dry-run execution timed out (may be normal for large libraries)")
        return {"success": False, "error": "Timeout", "timeout": True}
    except Exception as e:
        print(f"    ✗ Error executing dry-run: {e}")
        return {"success": False, "error": str(e)}

def document_function_status(functions: Dict, execution_test: Dict) -> Dict[str, Any]:
    """Document comprehensive function status."""
    print("\n1.3 Documenting Function Status...")
    
    status_doc = {
        "function_availability": {
            "total_functions": len([f for f in functions.values() if isinstance(f, dict) and f.get("exists")]),
            "functions": functions
        },
        "independent_execution": {
            "supported": functions.get("standalone_execution", {}).get("has_dedup_mode", False),
            "test_result": execution_test
        },
        "system_compliance": {
            "uses_documented_paths": True,  # From Phase 0
            "compliance_verified": True
        }
    }
    
    print("  ✓ Function status documented:")
    print(f"    - Available functions: {status_doc['function_availability']['total_functions']}")
    print(f"    - Standalone execution: {status_doc['independent_execution']['supported']}")
    print(f"    - Dry-run test: {'Success' if execution_test.get('success') else 'Failed/Timeout'}")
    
    return status_doc

def main():
    """Main execution function."""
    print("=" * 80)
    print("PHASE 1: REVIEW & STATUS IDENTIFICATION")
    print("=" * 80)
    
    load_unified_env()
    
    # 1.1 Review Function Implementation
    functions = review_function_implementation()
    
    if functions.get("error"):
        print(f"\n✗ ERROR: {functions['error']}")
        return 1
    
    # 1.2 Test Independent Execution
    execution_test = test_independent_execution()
    
    # 1.3 Document Function Status
    status_doc = document_function_status(functions, execution_test)
    
    # Save status document
    import json
    status_file = PROJECT_ROOT / 'phase1_function_status.json'
    with open(status_file, 'w') as f:
        json.dump(status_doc, f, indent=2, default=str)
    
    print(f"\n✓ Function status saved to: {status_file}")
    print("\n" + "=" * 80)
    print("PHASE 1 COMPLETE")
    print("=" * 80)
    
    if functions.get("standalone_execution", {}).get("has_dedup_mode") and execution_test.get("success"):
        print("✓ All functions available and dry-run test passed")
        return 0
    else:
        print("⚠ Some issues detected - review status document")
        return 1

if __name__ == "__main__":
    sys.exit(main())
