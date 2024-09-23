#!/bin/bash

bash ./train_g2p.sh
cd ~/data
bash scripts/prepare_alignment.sh input/ output/arranged_corpus

## Using only speaker ids for speaker identification
mfa train --speaker_characters 3 --g2p_model_path output/models/g2p.zip -j8 output/arranged_corpus scripts/alignment_data/word2pron.txt output/models/am

## Now align the data
mfa align --speaker_characters 3 --g2p_model_path output/models/g2p.zip -j8 output/arranged_corpus scripts/alignment_data/word2pron.txt output/models/am.zip output/alignment
