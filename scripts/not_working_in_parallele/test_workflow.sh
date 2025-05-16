#!/bin/bash

# Source the project variables
source project.yml

# Function to check if backup exists and backup word folder
backup_word_folder() {
    local workflow_name="$1"
    local word_folder="${vars.assets_folder}/word_${workflow_name}"
    local backup_folder="${word_folder}_$(date +%Y%m%d_%H%M%S)"
    
    # Check if word folder exists
    if [ -d "$word_folder" ]; then
        echo "Word folder already exists at $word_folder, skipping..."
        return 1
    fi
    
    # Check if any backup exists for this workflow
    if ls "${word_folder}_"* 1> /dev/null 2>&1; then
        echo "Backup already exists for $workflow_name, skipping..."
        return 1
    fi
    
    return 0
}

# Test Qwen 2B workflows
test_qwen_2b() {
    if backup_word_folder "qwen2b"; then
        echo "Running test-qwen-2b workflow..."
        weasel run archive-to-word-qwen-2b
    fi
}

test_qwen_2b_segmented() {
    if backup_word_folder "qwen2b_segmented"; then
        echo "Running test-qwen-2b-segmented workflow..."
        weasel run archive-to-word-qwen-2b-segmented
    fi
}

# Test Qwen 7B workflows
test_qwen_7b() {
    if backup_word_folder "qwen7b"; then
        echo "Running test-qwen-7b workflow..."
        weasel run archive-to-word-qwen-7b
    fi
}

test_qwen_7b_segmented() {
    if backup_word_folder "qwen7b_segmented"; then
        echo "Running test-qwen-7b-segmented workflow..."
        weasel run archive-to-word-qwen-7b-segmented
    fi
}

# Test Qwen Max workflows
test_qwen_max() {
    if backup_word_folder "qwenmax"; then
        echo "Running test-qwen-max workflow..."
        weasel run archive-to-word-qwen-max
    fi
}

test_qwen_max_segmented() {
    if backup_word_folder "qwenmax_segmented"; then
        echo "Running test-qwen-max-segmented workflow..."
        weasel run archive-to-word-qwen-max-segmented
    fi
}

# Test LMStudio workflows
test_lmstudio() {
    if backup_word_folder "lmstudio"; then
        echo "Running test-lmstudio workflow..."
        weasel run archive-to-word-lmstudio
    fi
}

test_lmstudio_segmented() {
    if backup_word_folder "lmstudio_segmented"; then
        echo "Running test-lmstudio-segmented workflow..."
        weasel run archive-to-word-lmstudio-segmented
    fi
}

# Main function to run all tests
run_all_tests() {
    echo "Starting test workflows..."
    
    # Run Qwen 2B tests
    test_qwen_2b
    test_qwen_2b_segmented
    
    # Run Qwen 7B tests
    test_qwen_7b
    test_qwen_7b_segmented
    
    # Run Qwen Max tests
    test_qwen_max
    test_qwen_max_segmented
    
    # Run LMStudio tests
    test_lmstudio
    test_lmstudio_segmented
    
    echo "All test workflows completed."
}

# Run all tests if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    run_all_tests
fi 