#!/bin/bash

# Function to display usage information
usage() {
  echo "Usage: $0 <path_to_csv_file>"
  echo "This script reads a CSV file with two columns (name and id) and no header."
  echo "It iterates through each line and prints the name and id."
  exit 1
}

# Check if an argument is provided
if [ $# -eq 0 ]; then
  usage
fi

# Assign the first argument to a variable
csv_file="$1"

# Check if the file exists
if [ ! -f "$csv_file" ]; then
  echo "Error: File '$csv_file' does not exist."
  exit 1
fi

# Read the CSV file line by line
while IFS=',' read -r name id; do
  # Trim leading and trailing whitespace from name and id
  name=$(echo "$name" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
  id=$(echo "$id" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')

  ./organize_voice.py \
    --orig_name $name \
    --dest_name $id \
    --source data/EmoSpeech/ \
    --dest data/processed \
    --emotion-script data/EmoSpeech/speaker\ scripts/t3_intensity_script_${name}.txt \
    --addenda-script data/EmoSpeech/speaker\ scripts/t3_addendum.txt \
    --verbose \
    --flac \
    --force

  # Print the name and id
  echo "Name: $name, ID: $id"
done <"$csv_file"

echo "Finished processing the CSV file."
