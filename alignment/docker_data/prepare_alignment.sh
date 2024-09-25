#!/bin/bash

if [[ $# -ne 2 ]]; then
  echo "Usage $0 prepare_alignment.sh <input_data_dir> <arranged_data_dir>"
  echo "This script takes in a data directory containing nested and emotion "
  echo "directories with an index file for each speaker"
  echo "and rearranges it to match with MFA's preferred corpus structure"
  echo "Which has one flat directory structure with .wav files and associated .lab files in one directory"
  exit 0
fi

input_data_dir=$1
arranged_data_dir=$2

if [[ ! -d $input_data_dir ]]; then
  echo "$input_data_dir does not exist, exiting..."
fi

if [[ -d $arranged_data_dir ]]; then
  echo "output directory already exists... Continue(y/n)?"
  read cont
  if [[ $cont -ne "y" ]]; then
    echo "exiting..."
    exit 0
  fi
fi

if [[ ! -d $arranged_data_dir ]]; then
  mkdir -p $arranged_data_dir
fi

for idxfile in $input_data_dir/*/index.tsv; do
  while read -r line; do
    IFS=$'\t' read -r fname spkid emotion intensity text <<<$line
    # Only create .lab file if .flac file exists.
    fpath=${input_data_dir}/${spkid}/${emotion}/${fname}
    if [[ -e $fpath ]]; then
      echo $text >${arranged_data_dir}/${fname%.flac}.lab
      ln -s ${fpath} ${arranged_data_dir}/${fname}
    else
      echo "$fpath does not exist. Skipping..."
    fi
  done <$idxfile
done
