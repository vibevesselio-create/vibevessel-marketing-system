#!/usr/bin/env python3
"""
Agent Handoff Processing Verification Test

Verifies that agent handoff files were properly processed and moved to
02_processed/ directories.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Base path for agent triggers
AGENT_TRIGGERS_BASE = Path(__file__).parent.parent / "agents" / "agent-triggers"


def find_processed_handoffs():
    """Find all RETURN handoff files in 02_processed directories."""
    processed_files = []
    
    for agent_dir in AGENT_TRIGGERS_BASE.iterdir():
        if not agent_dir.is_dir():
            continue
        
        processed_dir = agent_dir / "02_processed"
        if not processed_dir.exists():
            continue
        
        for file in processed_dir.glob("*RETURN*.json"):
            processed_files.append({
                'agent': agent_dir.name,
                'file': file.name,
                'path': file,
                'timestamp': file.stat().st_mtime
            })
    
    return processed_files


def verify_handoff_structure(file_path):
    """Verify that a handoff file has proper structure."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        required_fields = ['type', 'timestamp', 'executing_agent', 'execution_summary']
        missing_fields = [field for field in required_fields if field not in data]
        
        return {
            'valid': len(missing_fields) == 0,
            'missing_fields': missing_fields,
            'data': data
        }
    except json.JSONDecodeError as e:
        return {
            'valid': False,
            'error': f'Invalid JSON: {e}',
            'data': None
        }
    except Exception as e:
        return {
            'valid': False,
            'error': str(e),
            'data': None
        }


def verify_session_handoffs():
    """Verify handoffs processed in this session (2026-01-18)."""
    print("\n=== Session Handoff Verification ===")
    
    processed_files = find_processed_handoffs()
    
    # Filter for files from 2026-01-18
    session_files = []
    for file_info in processed_files:
        file_date = datetime.fromtimestamp(file_info['timestamp']).date()
        if file_date == datetime(2026, 1, 18).date():
            session_files.append(file_info)
    
    print(f"Session handoff files found: {len(session_files)}")
    
    expected_files = [
        'RETURN__System-Prompts-Workflows-Integration-Gap-Analysis__Claude-Code-Agent.json',
        'RETURN__Webhook-Server-Progress-Review__Claude-Code-Agent.json',
        'RETURN__GAS-API-OAuth-Credentials-Troubleshooting__Claude-Code-Agent.json',
        'RETURN__DriveSheetsSync-Implementation-Refinement__Claude-Code-Agent.json',
        'RETURN__Music-Workflow-Implementation-Refinement__Claude-Code-Agent.json',
    ]
    
    found_files = []
    for file_info in session_files:
        found_files.append(file_info['file'])
        print(f"  ✅ {file_info['agent']}/{file_info['file']}")
    
    # Check for expected files
    missing_files = []
    for expected in expected_files:
        if not any(expected in f for f in found_files):
            missing_files.append(expected)
    
    if missing_files:
        print(f"\n⚠️  Missing expected files: {len(missing_files)}")
        for missing in missing_files:
            print(f"  - {missing}")
    
    # Verify file structure
    print("\n=== File Structure Verification ===")
    valid_count = 0
    invalid_count = 0
    
    for file_info in session_files:
        result = verify_handoff_structure(file_info['path'])
        if result['valid']:
            valid_count += 1
            print(f"  ✅ {file_info['file']}")
        else:
            invalid_count += 1
            print(f"  ❌ {file_info['file']}: {result.get('error', result.get('missing_fields', 'Unknown error'))}")
    
    print(f"\nValid files: {valid_count}/{len(session_files)}")
    print(f"Invalid files: {invalid_count}/{len(session_files)}")
    
    return {
        'session_files': len(session_files),
        'valid_files': valid_count,
        'invalid_files': invalid_count,
        'missing_expected': len(missing_files)
    }


def main():
    """Run handoff verification tests."""
    print("=" * 60)
    print("Agent Handoff Processing Verification")
    print("=" * 60)
    
    if not AGENT_TRIGGERS_BASE.exists():
        print(f"❌ ERROR: Agent triggers directory not found: {AGENT_TRIGGERS_BASE}")
        return 1
    
    results = verify_session_handoffs()
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Session handoff files: {results['session_files']}")
    print(f"Valid files: {results['valid_files']}")
    print(f"Invalid files: {results['invalid_files']}")
    print(f"Missing expected: {results['missing_expected']}")
    
    all_passed = (
        results['session_files'] >= 5 and
        results['invalid_files'] == 0 and
        results['missing_expected'] == 0
    )
    
    print(f"\nOverall Status: {'✅ ALL TESTS PASSED' if all_passed else '⚠️ SOME ISSUES DETECTED'}")
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
