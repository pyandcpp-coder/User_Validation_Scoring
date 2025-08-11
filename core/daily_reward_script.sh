#!/bin/bash
# daily_reward_script.sh
# This script should be run daily (e.g., via cron) to distribute rewards

# Configuration
API_BASE_URL="http://localhost:8000"  # Change to your API URL
LOG_FILE="/var/log/daily_rewards.log"

# Function to log messages with timestamp
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_message "=== Starting Daily Reward Distribution ==="

# First, get a summary to review what will happen
log_message "Getting daily summary..."
SUMMARY_RESPONSE=$(curl -s -X GET "$API_BASE_URL/admin/daily-summary")

if [ $? -eq 0 ]; then
    log_message "Daily summary retrieved successfully"
    echo "$SUMMARY_RESPONSE" | python3 -m json.tool >> "$LOG_FILE" 2>&1
else
    log_message "ERROR: Failed to get daily summary"
    exit 1
fi

# Run the actual daily analysis and reward distribution
log_message "Running daily analysis and reward distribution..."
ANALYSIS_RESPONSE=$(curl -s -X POST "$API_BASE_URL/admin/run-daily-analysis")

if [ $? -eq 0 ]; then
    log_message "Daily analysis completed successfully"
    echo "$ANALYSIS_RESPONSE" | python3 -m json.tool >> "$LOG_FILE" 2>&1
    
    # Check if the response indicates success
    if echo "$ANALYSIS_RESPONSE" | grep -q '"status": "success"'; then
        log_message "✅ Daily rewards distributed successfully!"
        exit 0
    else
        log_message "❌ Daily analysis completed but may have encountered errors"
        exit 1
    fi
else
    log_message "ERROR: Failed to run daily analysis"
    exit 1
fi

# Example cron job entry (add this to your crontab):
# Run daily at 1:00 AM UTC
# 0 1 * * * /path/to/daily_reward_script.sh

# To add to cron:
# crontab -e
# Then add the line above (uncommented)