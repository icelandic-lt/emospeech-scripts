#!/bin/bash

# get prondict and extract relevant columns
cd alignment_data
wget https://raw.githubusercontent.com/grammatek/iceprondict/refs/heads/master/dictionaries/ice_pron_dict_complete.csv
cut -d$'\t' -f-2 ice_pron_dict_complete.csv | tail -n+2 >word2pron.tsv

cd ~/data
mfa train_g2p scripts/alignment_data/word2pron.txt output/models/g2p
