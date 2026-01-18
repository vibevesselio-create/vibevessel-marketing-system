#!/usr/bin/env python3
"""
Continuous Handoff Task System Runner
=====================================

This script runs the continuous handoff processor that:
1. Processes tasks from the Agent-Tasks database in Notion
2. Creates handoff trigger files in agent 01_inbox folders
3. Assigns tasks to the most appropriate agent based on capabilities
4. Creates review handoff tasks back to Cursor MM1 Agent when tasks complete
5. Runs continuously until 0 tasks remain

Usage:
    python3 scripts/run_continuous_handoff.py [--interval 600] [--once]

Options:
    --interval N    Interval between iterations in seconds (default: 600 = 10 minutes)
    --once          Process one task and exit (for testing)
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import and run the continuous handoff processor
from scripts.continuous_handoff_processor import main

if __name__ == "__main__":
    main()



























