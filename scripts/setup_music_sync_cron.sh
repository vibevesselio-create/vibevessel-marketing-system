#!/bin/bash

# Setup cron job for Music Track Sync Workflow
# This script creates a cron job for automated music sync execution

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MUSIC_SYNC_SCRIPT="$SCRIPT_DIR/music_track_sync_auto_detect.py"
LOG_FILE="$PROJECT_DIR/logs/music_sync_cron.log"
VENV_PATH="/Users/brianhellemn/Projects/venv-unified-MM1/bin/activate"

# Default schedule: Every 6 hours (configurable via environment variable)
MUSIC_SYNC_SCHEDULE="${MUSIC_SYNC_SCHEDULE:-0 */6 * * *}"

# Make the Python script executable
chmod +x "$MUSIC_SYNC_SCRIPT"

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

# Function to add cron job
add_cron_job() {
    local schedule="$1"
    local command="$2"
    local description="$3"
    
    # Check if cron job already exists
    if crontab -l 2>/dev/null | grep -q "$MUSIC_SYNC_SCRIPT"; then
        echo "Music sync cron job already exists. Removing old entry..."
        crontab -l 2>/dev/null | grep -v "$MUSIC_SYNC_SCRIPT" | crontab -
    fi
    
    # Add new cron job with logging
    (crontab -l 2>/dev/null; echo "$schedule $command") | crontab -
    echo "✅ Added cron job for $description"
    echo "   Schedule: $schedule"
    echo "   Command: $command"
}

# Function to remove cron jobs
remove_cron_jobs() {
    echo "Removing music sync cron job..."
    crontab -l 2>/dev/null | grep -v "$MUSIC_SYNC_SCRIPT" | crontab -
    echo "✅ Music sync cron job removed"
}

# Function to list cron jobs
list_cron_jobs() {
    echo "Current music sync cron jobs:"
    echo "----------------------------------------"
    crontab -l 2>/dev/null | grep "$MUSIC_SYNC_SCRIPT" || echo "No music sync cron jobs found"
    echo "----------------------------------------"
}

# Main setup function
setup_cron_job() {
    echo "Setting up cron job for Music Track Sync Workflow..."
    echo "Project directory: $PROJECT_DIR"
    echo "Script: $MUSIC_SYNC_SCRIPT"
    echo "Log file: $LOG_FILE"
    echo "Schedule: $MUSIC_SYNC_SCHEDULE"
    echo ""
    
    # Build the cron command
    # Uses source to activate venv, changes to project dir, runs script with logging
    SYNC_CMD="cd $PROJECT_DIR && source $VENV_PATH && python3 $MUSIC_SYNC_SCRIPT >> $LOG_FILE 2>&1"
    
    add_cron_job "$MUSIC_SYNC_SCHEDULE" "$SYNC_CMD" "Music Track Sync"
    
    echo ""
    echo "✅ Cron job setup complete!"
    echo ""
    echo "Scheduled job:"
    echo "- Music Track Sync: $MUSIC_SYNC_SCHEDULE"
    echo "  (Default: Every 6 hours at :00 minutes)"
    echo ""
    echo "To view current cron jobs: $0 list"
    echo "To remove cron job: $0 remove"
    echo "To change schedule, set MUSIC_SYNC_SCHEDULE environment variable:"
    echo "  export MUSIC_SYNC_SCHEDULE='0 */4 * * *'  # Every 4 hours"
    echo "  export MUSIC_SYNC_SCHEDULE='0 * * * *'    # Every hour"
    echo "  export MUSIC_SYNC_SCHEDULE='0 0 * * *'    # Daily at midnight"
}

# Test the setup
test_setup() {
    echo "Testing music sync script..."
    cd "$PROJECT_DIR" && source "$VENV_PATH" && python3 "$MUSIC_SYNC_SCRIPT" --help
    if [ $? -eq 0 ]; then
        echo "✅ Script is executable and working"
    else
        echo "❌ Script test failed"
        exit 1
    fi
}

# Parse command line arguments
case "${1:-setup}" in
    setup)
        setup_cron_job
        ;;
    remove)
        remove_cron_jobs
        ;;
    list)
        list_cron_jobs
        ;;
    test)
        test_setup
        ;;
    *)
        echo "Usage: $0 {setup|remove|list|test}"
        echo ""
        echo "Commands:"
        echo "  setup  - Set up the music sync cron job (default)"
        echo "  remove - Remove the music sync cron job"
        echo "  list   - List current music sync cron jobs"
        echo "  test   - Test the music sync script"
        echo ""
        echo "Environment Variables:"
        echo "  MUSIC_SYNC_SCHEDULE - Cron schedule expression (default: '0 */6 * * *')"
        exit 1
        ;;
esac
