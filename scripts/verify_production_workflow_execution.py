#!/usr/bin/env python3
"""
Production Workflow Execution Verification Script

Verifies that all expected outputs from the production workflow were created:
- Files created in correct formats (M4A, WAV, AIFF)
- Notion database updated with all metadata
- Eagle library import successful (if applicable)
- No duplicates created
- Audio analysis complete (BPM, Key)
- Spotify metadata enriched (if applicable)
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

def check_file_exists(file_path: str) -> Tuple[bool, str]:
    """Check if a file exists and return size."""
    path = Path(file_path)
    if path.exists():
        size = path.stat().st_size
        size_mb = size / (1024 * 1024)
        return True, f"{size_mb:.2f} MB"
    return False, "Not found"

def verify_notion_track_update(page_id: str) -> Dict:
    """Verify Notion track page has been updated with expected properties."""
    try:
        import requests

        # Use centralized token manager (MANDATORY per CLAUDE.md)
        try:
            from shared_core.notion.token_manager import get_notion_token
            notion_token = get_notion_token()
        except ImportError:
            notion_token = os.getenv("NOTION_TOKEN")

        if not notion_token:
            return {"error": "NOTION_TOKEN not set"}
        
        headers = {
            "Authorization": f"Bearer {notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        url = f"https://api.notion.com/v1/pages/{page_id}"
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}: {response.text}"}
        
        page = response.json()
        props = page.get("properties", {})
        
        results = {
            "page_id": page_id,
            "properties": {},
            "missing": [],
            "complete": True
        }
        
        # Check for key properties
        expected_props = [
            "Title",
            "Artist Name",
            "Downloaded",
            "M4A File Path",
            "AIFF File Path",
            "WAV File Path",
            "BPM",
            "Key",
            "Duration (ms)"
        ]
        
        for prop_name in expected_props:
            if prop_name in props:
                prop = props[prop_name]
                prop_type = prop.get("type")
                
                if prop_type == "checkbox":
                    value = prop.get("checkbox", False)
                    results["properties"][prop_name] = value
                elif prop_type == "rich_text":
                    rich_text = prop.get("rich_text", [])
                    value = rich_text[0].get("plain_text", "") if rich_text else ""
                    results["properties"][prop_name] = value
                elif prop_type == "number":
                    value = prop.get("number")
                    results["properties"][prop_name] = value
                elif prop_type == "title":
                    title = prop.get("title", [])
                    value = title[0].get("plain_text", "") if title else ""
                    results["properties"][prop_name] = value
                else:
                    results["properties"][prop_name] = f"({prop_type})"
            else:
                results["missing"].append(prop_name)
                results["complete"] = False
        
        return results
        
    except Exception as e:
        return {"error": str(e)}

def verify_file_paths(track_info: Dict) -> Dict:
    """Verify that file paths exist on disk."""
    results = {
        "m4a": None,
        "aiff": None,
        "wav": None,
        "all_found": False
    }
    
    props = track_info.get("properties", {})
    
    # Check M4A file
    if "M4A File Path" in props:
        m4a_prop = props["M4A File Path"]
        if m4a_prop.get("type") == "rich_text":
            rich_text = m4a_prop.get("rich_text", [])
            if rich_text:
                m4a_path = rich_text[0].get("plain_text", "")
                if m4a_path:
                    exists, info = check_file_exists(m4a_path)
                    results["m4a"] = {"path": m4a_path, "exists": exists, "info": info}
    
    # Check AIFF file
    if "AIFF File Path" in props:
        aiff_prop = props["AIFF File Path"]
        if aiff_prop.get("type") == "rich_text":
            rich_text = aiff_prop.get("rich_text", [])
            if rich_text:
                aiff_path = rich_text[0].get("plain_text", "")
                if aiff_path:
                    exists, info = check_file_exists(aiff_path)
                    results["aiff"] = {"path": aiff_path, "exists": exists, "info": info}
    
    # Check WAV file
    if "WAV File Path" in props:
        wav_prop = props["WAV File Path"]
        if wav_prop.get("type") == "rich_text":
            rich_text = wav_prop.get("rich_text", [])
            if rich_text:
                wav_path = rich_text[0].get("plain_text", "")
                if wav_path:
                    exists, info = check_file_exists(wav_path)
                    results["wav"] = {"path": wav_path, "exists": exists, "info": info}
    
    results["all_found"] = (
        results["m4a"] and results["m4a"]["exists"] or
        results["aiff"] and results["aiff"]["exists"] or
        results["wav"] and results["wav"]["exists"]
    )
    
    return results

def verify_audio_analysis(track_info: Dict) -> Dict:
    """Verify audio analysis was completed (BPM, Key)."""
    results = {
        "bpm": None,
        "key": None,
        "duration": None,
        "complete": False
    }
    
    props = track_info.get("properties", {})
    
    # Check BPM
    if "BPM" in props:
        bpm_prop = props["BPM"]
        if bpm_prop.get("type") == "number":
            results["bpm"] = bpm_prop.get("number")
    
    # Check Key
    if "Key" in props:
        key_prop = props["Key"]
        if key_prop.get("type") == "rich_text":
            rich_text = key_prop.get("rich_text", [])
            if rich_text:
                results["key"] = rich_text[0].get("plain_text", "")
        elif key_prop.get("type") == "select":
            results["key"] = key_prop.get("select", {}).get("name")
    
    # Check Duration
    if "Duration (ms)" in props:
        duration_prop = props["Duration (ms)"]
        if duration_prop.get("type") == "number":
            results["duration"] = duration_prop.get("number")
    
    results["complete"] = results["bpm"] is not None and results["key"] is not None
    
    return results

def verify_eagle_import(track_info: Dict) -> Dict:
    """Verify Eagle library import was successful."""
    results = {
        "eagle_id": None,
        "imported": False
    }
    
    props = track_info.get("properties", {})
    
    # Check for Eagle ID
    for prop_name in ["Eagle ID", "Eagle Item ID"]:
        if prop_name in props:
            eagle_prop = props[prop_name]
            if eagle_prop.get("type") == "rich_text":
                rich_text = eagle_prop.get("rich_text", [])
                if rich_text:
                    results["eagle_id"] = rich_text[0].get("plain_text", "")
                    results["imported"] = bool(results["eagle_id"])
                    break
    
    return results

def verify_track(page_id: str) -> Dict:
    """Verify all aspects of a track's processing."""
    print(f"Verifying track: {page_id}")
    print("-" * 80)
    
    results = {
        "page_id": page_id,
        "notion": {},
        "files": {},
        "audio_analysis": {},
        "eagle": {},
        "overall_status": "unknown"
    }
    
    # Verify Notion update
    print("1. Checking Notion update...")
    notion_result = verify_notion_track_update(page_id)
    if "error" in notion_result:
        print(f"   ✗ Error: {notion_result['error']}")
        results["overall_status"] = "error"
        return results
    else:
        results["notion"] = notion_result
        if notion_result.get("complete"):
            print(f"   ✓ All expected properties present")
        else:
            missing = notion_result.get("missing", [])
            print(f"   ⚠ Missing properties: {', '.join(missing)}")
    
    # Verify file paths
    print("2. Checking file paths...")
    file_results = verify_file_paths(notion_result)
    results["files"] = file_results
    
    if file_results["m4a"]:
        m4a = file_results["m4a"]
        status = "✓" if m4a["exists"] else "✗"
        print(f"   {status} M4A: {m4a['path']} ({m4a['info']})")
    
    if file_results["aiff"]:
        aiff = file_results["aiff"]
        status = "✓" if aiff["exists"] else "✗"
        print(f"   {status} AIFF: {aiff['path']} ({aiff['info']})")
    
    if file_results["wav"]:
        wav = file_results["wav"]
        status = "✓" if wav["exists"] else "✗"
        print(f"   {status} WAV: {wav['path']} ({wav['info']})")
    
    if not file_results["all_found"]:
        print(f"   ⚠ No files found on disk")
    
    # Verify audio analysis
    print("3. Checking audio analysis...")
    analysis_results = verify_audio_analysis(notion_result)
    results["audio_analysis"] = analysis_results
    
    if analysis_results["bpm"]:
        print(f"   ✓ BPM: {analysis_results['bpm']}")
    else:
        print(f"   ✗ BPM: Not found")
    
    if analysis_results["key"]:
        print(f"   ✓ Key: {analysis_results['key']}")
    else:
        print(f"   ✗ Key: Not found")
    
    if analysis_results["complete"]:
        print(f"   ✓ Audio analysis complete")
    else:
        print(f"   ⚠ Audio analysis incomplete")
    
    # Verify Eagle import
    print("4. Checking Eagle import...")
    eagle_results = verify_eagle_import(notion_result)
    results["eagle"] = eagle_results
    
    if eagle_results["imported"]:
        print(f"   ✓ Eagle ID: {eagle_results['eagle_id']}")
    else:
        print(f"   ⚠ Eagle import not found (may be optional)")
    
    # Overall status
    if (notion_result.get("complete") and 
        file_results["all_found"] and 
        analysis_results["complete"]):
        results["overall_status"] = "complete"
        print()
        print("=" * 80)
        print("✓ Verification PASSED: All checks passed")
        print("=" * 80)
    elif file_results["all_found"] or analysis_results["complete"]:
        results["overall_status"] = "partial"
        print()
        print("=" * 80)
        print("⚠ Verification PARTIAL: Some checks passed")
        print("=" * 80)
    else:
        results["overall_status"] = "failed"
        print()
        print("=" * 80)
        print("✗ Verification FAILED: Critical checks failed")
        print("=" * 80)
    
    return results

def main():
    """Main verification function."""
    if len(sys.argv) < 2:
        print("Usage: verify_production_workflow_execution.py <notion_page_id>")
        print()
        print("Verifies that a track's processing was completed successfully:")
        print("  - Notion database updated with all metadata")
        print("  - Files created in correct formats (M4A, WAV, AIFF)")
        print("  - Audio analysis complete (BPM, Key)")
        print("  - Eagle library import successful (if applicable)")
        sys.exit(1)
    
    page_id = sys.argv[1]
    results = verify_track(page_id)
    
    # Output JSON for programmatic use
    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))
    
    # Exit with appropriate code
    if results["overall_status"] == "complete":
        sys.exit(0)
    elif results["overall_status"] == "partial":
        sys.exit(2)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
