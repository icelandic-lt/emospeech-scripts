#!/bin/bash

# Function to display usage information
usage() {
  echo "Usage: $0 <path_to_root_dir> [--stage <num>] [--stop-stage <num>]"
  echo "This script unzips all zip files from the specified directory into a 'data' directory"
  echo "and then processes subdirectories."
  echo ""
  echo "Options:"
  echo "  --stage <num>      Start execution from this stage (default: 1)"
  echo "  --stop-stage <num> Stop execution after this stage (default: 3)"
  echo ""
  echo "Stages:"
  echo "  1: Unzip files from root directory"
  echo "  2: Process subdirectories"
  echo "  3: Cleanup (placeholder)"
  echo ""
  echo "Expected structure:"
  echo "  The zip files processed by this script are expected to, when unzipped, combine together to create"
  echo "  a directory named EmoSpeech, which itself contains subdirectories, some of which contain zips"
  echo "  e.g."
  echo "  EmoSpeech"
  echo "  ├─name1"
  echo "  │ ├──name1_happy.zip"
  echo "  │ ├──name1_sad.zip"
  echo "  │ ├──name1_angry.zip"
  echo "  │ ├──name1_surprised.zip"
  echo "  │ …"
  echo "  │ └──name1_addendum_style2.zip"
  echo "  ├─name2"
  echo "  │ └…"
  echo "  …"
  echo "  ├─speaker_scripts"
  echo "  │ ├──name1_script.txt"
  echo "  │ ├──name2_script.txt"
  echo "  │ ├──name3_script.txt"
  echo "  │ …"
  echo "  │ └──nameN_script.txt"
  exit 1
}

# Initialize variables
start_stage=1
stop_stage=3
root_dir=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
  --stage)
    start_stage=$2
    shift 2
    ;;
  --stop-stage)
    stop_stage=$2
    shift 2
    ;;
  --help)
    usage
    ;;
  *)
    if [ -z "$root_dir" ]; then
      root_dir=$1
      shift
    else
      echo "Unknown argument: $1"
      usage
    fi
    ;;
  esac
done

# Check if root_dir is provided
if [ -z "$root_dir" ]; then
  echo "Error: No root directory specified."
  usage
fi

# Check if the directory exists
if [ ! -d "$root_dir" ]; then
  echo "Error: Directory '$root_dir' does not exist."
  exit 1
fi

# Create a 'data' directory in the current working directory
data_dir="./data"
mkdir -p "$data_dir"

# Stage 1: Unzip files from root directory
stage1() {
  echo "Stage 1: Unzipping files from root directory"
  if ! ls "$root_dir"/*.zip &>/dev/null; then
    echo "Error: No zip files found in '$root_dir'."
    exit 1
  fi
  for zip_file in "$root_dir"/*.zip; do
    unzip -q "$zip_file" -d "$data_dir"
  done
  echo "All zip files have been extracted to $data_dir"
}

# Stage 2: Process subdirectories
stage2() {
  echo "Stage 2: Processing subdirectories"
  for subdir in "$data_dir"/EmoSpeech/*; do
    if [ -d "$subdir" ]; then
      subdir_name=$(basename "$subdir")
      if [[ "$subdir_name" != "Consent forms" && "$subdir_name" != "speaker scripts" ]]; then
        echo "Processing subdirectory: $subdir_name"
        for zip_file in "$subdir"/*.zip; do
          if [ -f "$zip_file" ]; then
            unzip -q "$zip_file" -d "$data_dir/EmoSpeech"
            rm "$zip_file"
            # dirname=${zip_file%.zip}
            # mv $dirname $subdir/${dirname#*_}
            echo "Unzipped and removed: $zip_file"
          fi
        done
        rm -r $subdir
      else
        echo "Skipping subdirectory: $subdir_name"
      fi
    fi
  done
}

# Stage 3: Cleanup (placeholder)
stage3() {
  echo "Stage 3: Cleanup (placeholder)"
  # Add any cleanup operations here if needed
  rm -r $data_dir/EmoSpeech/__MACOSX
  rm -r $data_dir/EmoSpeech/"Consent forms"
}

# Execute stages based on start_stage and stop_stage
for stage in $(seq $start_stage $stop_stage); do
  case $stage in
  1) stage1 ;;
  2) stage2 ;;
  3) stage3 ;;
  esac
done

echo "Script execution completed."
