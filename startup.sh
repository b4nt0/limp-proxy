#!/bin/bash
set -e

# Function to download remote config if LIMP_CONFIG starts with http:// or https://
download_remote_config() {
    if [[ "$LIMP_CONFIG" =~ ^https?:// ]]; then
        echo "Remote config detected: $LIMP_CONFIG"
        
        # Create temporary directory for downloaded config
        TEMP_DIR=$(mktemp -d)
        TEMP_CONFIG="$TEMP_DIR/config.yaml"
        
        echo "Downloading config to: $TEMP_CONFIG"
        
        # Download the config file with curl
        if curl -f -s -L "$LIMP_CONFIG" -o "$TEMP_CONFIG"; then
            echo "Config downloaded successfully"
            
            # Update LIMP_CONFIG to point to the downloaded file
            export LIMP_CONFIG="$TEMP_CONFIG"
            echo "Updated LIMP_CONFIG to: $LIMP_CONFIG"
        else
            echo "Failed to download config from: $LIMP_CONFIG"
            exit 1
        fi
    else
        echo "Using local config: $LIMP_CONFIG"
    fi
}

# Function to validate config file exists
validate_config() {
    if [ ! -f "$LIMP_CONFIG" ]; then
        echo "Configuration file not found: $LIMP_CONFIG"
        echo "Please ensure the config file exists or provide a valid remote URL"
        exit 1
    fi
    echo "Configuration file validated: $LIMP_CONFIG"
}

# Function to start the application
start_application() {
    echo "Starting LIMP application..."
    exec python main.py
}

# Main execution
main() {
    echo "=== LIMP Container Startup ==="
    echo "Initial LIMP_CONFIG: ${LIMP_CONFIG:-'not set'}"
    
    # Download remote config if needed
    download_remote_config
    
    # Validate config file exists
    validate_config
    
    # Start the application
    start_application
}

# Run main function
main "$@"
