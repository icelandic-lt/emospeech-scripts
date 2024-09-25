#!/bin/bash

## simple script to combine intensity scripts

cat data/EmoSpeech/speaker\ scripts/t3_intensity_script_*.txt |
  sed "s/  / /g" |
  cut -d' ' -f2,4- |
  cut -d'"' -f1 |
  sort | uniq |
  awk '{printf "u%03d %s\n", NR, $0}' \
    >t3_intensity_script_combined.txt
