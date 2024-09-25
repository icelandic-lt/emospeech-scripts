#!/bin/bash

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <input_dir> <output_dir>"
  echo "Example: $0 /path/to/input_dir /path/to/output_dir"
  exit 1
fi

input_dir="$1"
output_dir="$2"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

scripts_dir="$script_dir/docker_data"

if [ ! -d "$input_dir" ]; then
  echo "Error: Input directory '$input_dir' does not exist."
  exit 1
fi

if [ ! -d "$output_dir" ]; then
  echo "Output directory '$output_dir' does not exist. Creating it now..."
  mkdir -p "$output_dir"
fi

if [ ! -d "$scripts_dir" ]; then
  echo "Scripts directory '$scripts_dir' does not exist. Creating it now."
  mkdir -p "$scripts_dir"
fi

chmod -R 777 "$scripts_dir"
chmod -R 777 "$output_dir"

# Pull the latest MFA Docker image
echo "Pulling the latest MFA Docker image..."
docker pull mmcauliffe/montreal-forced-aligner:v3.1.3

# Run the Docker container
echo "Starting the MFA Docker container..."
docker run -it \
  -v "$input_dir":/home/mfauser/data/input \
  -v "$output_dir":/home/mfauser/data/output \
  -v "$scripts_dir":/home/mfauser/data/scripts \
  mmcauliffe/montreal-forced-aligner:latest

echo "MFA Docker container has been stopped."
