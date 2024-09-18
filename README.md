# Scripts for preparation of the emotional speech dataset

This repository provides scripts for recording and post-processing of emotional speech datasets.

![Version](https://img.shields.io/badge/Version-master-darkgreen)
![Python](https://img.shields.io/badge/python-3.9+-blue?logo=python&logoColor=white)
![CI Status](https://img.shields.io/badge/CI-[unavailable]-red)
![Docker](https://img.shields.io/badge/Docker-[unavailable]-red)

## Overview

This project has been created by the [Language and Voice Lab](https://lvl.ru.is/) at Reykjavík University in cooperation with [Grammatek ehf](https://www.grammatek.com) and is part of the [Icelandic Language Technology Programme](https://github.com/icelandic-lt/icelandic-lt).

- **Category:** [TTS](https://github.com/icelandic-lt/icelandic-lt/blob/main/doc/tts.md)
- **Domain:** Mac/Server/Workstation
- **Languages:** Python
- **Language Version/Dialect:**
  - Python: 3.9+
- **Audience**: Developers, Researchers
- **Origins:** [speechrecorder](??)

## Status
![Development](https://img.shields.io/badge/Development-darkviolet)

## System Requirements
- Operating System: Linux/OS-X

## Description

This project has been used to create Talrómur 3 <TODO: Link on Clarin once it's published>, the Icelandic emotional speech dataset. You can use this project to create voice recordings, be it emotional recordings or neutral recordings in combination with a workstation/laptop and appropriate audio recording equipment.

The recordings are done with a Python script that prints the utterance text with big letters on a text window and reacts to certain keys of a keyboard to quickly record the utterance, to play it, or navigate to the previous or next utterance. The same utterance can also be rerecorded any number of times. All recordings are saved to the directory given on command line. Although a bit raw, this script is an effective way to collect a new voice corpus quickly, given the appropriate equipment and a recording studio is available.

Following the recording of the raw audio files, we provide the script [organize_voice.py](organize_voice.py), to convert the raw recordings into a complete voice dataset that can be used for training a TTS voice model. If certain conventions are used for the directory names of the voice recordings, e.g. multiple recordings with the same voice but different styles, emotions, etc. these can be combined into the same voice dataset and also be losslessly converted into the FLAC format to save disk space.

Additionally, we provide an experimental script [vadiate.py](vadiate.py) that uses voice activity detection (VAD) to generate a list of voice activity timings for each dataset. This can be used, to e.g. surgically cut the beginning and end of a dataset recording to eliminate silence, or to split a recording into multiple pieces. The detection is mostly accurate, but for some strong emotions in combination with short utterances, voice activity is sometimes not detected correctly. 


## Installation

Install all requirements. We recommend using a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

```bash
pip install -r requirements.txt
```

## Start recordings 

**<to be done>**

## Create dataset

**<to be done>**

## Run VAD (voice activity detection)

```bash
python3 vadiate.py <source directory of audio files> <output.json>
```

There might be warnings for **"No speech detected in ..."** which means the VAD couldn't recognize any valid speech. Try parameter `--use-dynamic-threshold` to automatically reduce the confidence threshold. But always control the generated timings manually in those cases. Parameters of the VAD might be needed to be tweaked manually for your specific dataset for good values. Refer to the documentation of [Silero VAD](https://github.com/snakers4/silero-vad) for the exact meaning of all parameters of the used Python API.

## Acknowledgements
This project was funded by the Language Technology Programme for Icelandic 2019-2024. The program was funded by the Icelandic Ministry of Education, Science and Culture.