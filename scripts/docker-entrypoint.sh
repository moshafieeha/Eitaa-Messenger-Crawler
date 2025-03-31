#!/bin/bash
set -e

# Function to update config values
update_config() {
  python - <<EOF
import os
import re

# Path to config file
CONFIG_FILE = '/app/config.py'

# Read the file
with open(CONFIG_FILE, 'r') as f:
    content = f.read()

# Environment variables to look for and their corresponding config values
ENV_MAPPINGS = {
    'CHANNELS_FILE': 'CHANNELS_FILE',
    'OUTPUT_DIR': 'OUTPUT_DIR',
    'BIOS_DIR': 'BIOS_HISTORY_DIR',
    'LOGS_DIR': 'LOGS_DIR',
    'LOG_FILE': 'LOG_FILE',
    'META_DIR': 'META_DIR',
    'CRAWL_INTERVAL_SECONDS': 'CRAWL_INTERVAL_SECONDS',
    'CUMULATIVE_JSON_ITERATIONS': 'CUMULATIVE_JSON_ITERATIONS',
    'KAFKA_BROKER': 'KAFKA_BROKER',
    'KAFKA_TOPIC': 'TOPIC',
    'REFRESH_INTERVAL': 'REFRESH_INTERVAL'
}

# Update config values from environment variables
for env_var, config_var in ENV_MAPPINGS.items():
    if env_var in os.environ:
        env_value = os.environ[env_var]
        # Handle numeric values
        if env_var in ['CRAWL_INTERVAL_SECONDS', 'CUMULATIVE_JSON_ITERATIONS', 'REFRESH_INTERVAL']:
            pattern = f"self\\.{config_var} = .*"
            replacement = f"self.{config_var} = {env_value}  # Modified by entrypoint script"
        else:
            pattern = f"self\\.{config_var} = ['\\\"].*['\\\"]"
            replacement = f'self.{config_var} = "{env_value}"  # Modified by entrypoint script'
        
        content = re.sub(pattern, replacement, content)

# Write the updated content back
with open(CONFIG_FILE, 'w') as f:
    f.write(content)

print("Configuration updated successfully")
EOF
}

# Create necessary directories
mkdir -p /data/output/messages /data/output/bios /data/logs /data/meta

# Update config
echo "Updating configuration..."
update_config

# Execute the command
echo "Starting: $@"
exec "$@" 