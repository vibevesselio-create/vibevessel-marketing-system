#!/bin/bash
#
# Continuous Task Handoff Launcher
# =================================
#
# Runs the continuous handoff processor until 0 tasks remain in Agent-Tasks database.
# This script will:
# 1. Process the next highest-priority incomplete task
# 2. Create handoff files in appropriate agent inboxes
# 3. Create review handoffs when tasks complete
# 4. Continue until all tasks are complete
#
# Usage:
#   ./scripts/run_continuous_task_handoff.sh [--interval SECONDS]
#
# Default interval: 600 seconds (10 minutes) between iterations

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Default interval (10 minutes)
INTERVAL=${1:-600}

# Remove --interval flag if present
if [[ "$1" == "--interval" ]]; then
    INTERVAL=$2
fi

echo "============================================================"
echo "CONTINUOUS TASK HANDOFF PROCESSOR"
echo "============================================================"
echo ""
echo "This will continuously process Agent-Tasks until 0 tasks remain."
echo "Interval between checks: $INTERVAL seconds ($(echo "scale=1; $INTERVAL/60" | bc) minutes)"
echo ""
echo "Press Ctrl+C to stop at any time."
echo ""
echo "Starting continuous processing..."
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run the continuous processor
python3 scripts/continuous_handoff_processor.py --continuous --interval "$INTERVAL"
























