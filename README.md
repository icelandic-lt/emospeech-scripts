# Icelandic EmoSpeech

This repository provides scripts for recording and post-processing of emotional speech datasets.

![Version](https://img.shields.io/badge/Version-master-darkgreen)
![Python](https://img.shields.io/badge/python-3.9-blue?logo=python&logoColor=white)
![Python](https://img.shields.io/badge/python-3.10-blue?logo=python&logoColor=white)
![CI Status](https://img.shields.io/badge/CI-[unavailable]-red)
![Docker](https://img.shields.io/badge/Docker-[unavailable]-red)

## Overview

This project has been created by the [Language and Voice Lab](https://lvl.ru.is/) at Reykjavík University in cooperation with [Grammatek ehf](https://www.grammatek.com) and is part of the [Icelandic Language Technology Programme](https://github.com/icelandic-lt/icelandic-lt).

- **Category:** [TTS](https://github.com/icelandic-lt/icelandic-lt/blob/main/doc/tts.md)
- **Domain:** Laptop/Workstation
- **Languages:** Python
- **Language Version/Dialect:**
  - Python: 3.9, 3.10
- **Audience**: Developers, Researchers
- **Origins:** [speechrecorder #1](https://github.com/grammatek/speechrecorder), [#2](https://github.com/dan-wells/speechrecorder)

## Status
![Development](https://img.shields.io/badge/Development-darkviolet)

## System Requirements
- Operating System: Linux/OS-X, should work on Windows
- Recording: Audio Interface, good voice Mics

## Description

This project has been used to create Talrómur 3 <TODO: Link on Clarin once it's published>, the Icelandic emotional speech dataset. You can use this project to create voice recordings, be it emotional recordings or neutral recordings in combination with a workstation/laptop and appropriate audio recording equipment. We used OS-X for our recordings, but it should as well work on Linux and Windows.

The recordings are done with the Python script [rec.py](rec.py) that prints the utterance text with big letters on a text window and reacts to certain keys of a keyboard to quickly record the utterance, to play it, or navigate to the previous or next utterance. The same utterance can also be rerecorded any number of times. All recordings are saved to the directory given on command line. Although a bit raw, this script is an effective way to collect a new voice corpus quickly, given the appropriate equipment and a recording studio is available.

Following the recording of the raw audio files, we provide the script [organize_voice.py](organize_voice.py), to convert the raw recordings into a complete voice dataset that can be used for training a TTS voice model. If certain conventions are used for the directory names of the voice recordings, e.g. multiple recordings with the same voice but different styles, emotions, etc., then these can be combined into the same voice dataset and also be losslessly converted into the FLAC format to save disk space.

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

## Prepare recordings

Before you start recording, you should prepare a script with the utterances you want to record. The script should be a simple text file with one utterance per line. The utterances can be in any language you want. The script file has the following possible two formats:

For a script with emotion levels:

```text
( <unique id> "<emotion-level>: <utterance>" )
```

For a script without emotion levels. This format was used for recording our non-emotional "addendas":

```text
( <unique id> "<utterance>" )
```

You can see for both formats an example in the directory [scripts](scripts/).

The emotion levels can be from any monotonic numerical value range you want. We have used emotion levels 1-5 for the Talrómur 3 dataset and recorded 6 emotions: neutral, happy, sad, angry, surprised, and helpful. The emotion levels are used to control the emotion intensity of the speech in combination with the specific emotion. For neutral speech, we used emotion level 0.

To introduce variability in emotional intensity across speakers for the same utterance, we developed the Python script '[intensity_norm_script.py](intensity_norm_script.py). This tool generates unique emotion levels for each speaker, normalizing them to a given numerical range following a normal distribution with a given average and standard deviation.

The script parameters used to create our emotion levels were as follows:

```bash
python3 intensity_norm_script.py \
   --script scripts/t3_intensity_script \
   --output <output script> \
   --mean 3.2 \
   --std_dev 1.4 \
   --min_val 1 \
   --max_val 5
```

You can analyze the values of a given script by just providing the script file as a parameter. The script will print the mean, standard deviation, and the minimum and maximum values of the emotion levels.

You can also only generate the numeric values on stdout by not providing the `--output` and `--script` parameters.

The parameter `--plot` is always optional and plots the distribution of the analyzed/generated emotion values. 

## Record dataset 

The script [rec.py](rec.py) is used for recording the raw voice samples. It takes the following parameters:

```bash
python3 rec.py \
     --audio-in <audio input device> \
     --audio-out <audio output device> \
     --recdir <directory to save recordings> \
     --sr <sample rate, 44100 by default> \
     --bits <bits per sample (16, 24), 16 by default> \
     --script <script file>
```

You can either specify the audio input and output devices by their names or by their indices. The indices can be found by running the script without any parameters. The script will list all available devices and their indices. You can as well get a list of all available devices by running the script with the parameter `--show-devices`.

The following keys are used for controlling the script:

- **Space**: Start/Stop to record the current utterance. You can rerecord each utterance as often as you want.
- **P**: Play the current utterance
- **Cursor down**: Go to the next utterance
- **Cursor up**: Go to the previous utterance
- **Q**: To quit

Additionally, you can choose to start not from the beginning of the given script but from a specific utterance index by providing the parameter `--start-idx <utterance number>`. This is useful if you want to rerecord a specific utterance or if you want to continue recording after a break.

Each recording is placed directly inside the directory given by the parameter `--recdir`. The recordings are named according to the script id's and followed by the recording attempt number _1/_2/_3/... You can rerecord each utterance as often as you want.

E.g. if you have the following script:

```text
( t3_001 "2: Hello, how are you?" )
( t3_002 "5: I am fine, thank you." )
( t3_003 "1: What is your name?" )
...
```
Then the recordings will be saved e.g. as:

```text
t3_001_1.wav
t3_001_2.wav
t3_002_1.wav
t3_002_2.wav
t3_002_3.wav
t3_003_1.wav
...
```

### Directory naming convention

If you follow the convention to name your recording directories as `<voice-name>_<emotion>/`, you can easily combine multiple recordings of the same speaker into one dataset with the script [organize_voice.py](organize_voice.py). The script will automatically recognize the emotion and emotion level of each recording and save it to the metadata file `index.tsv` inside the destination directory. Please make sure to always use the same utterance script for all recordings of the same speaker.

## Create dataset

A voice dataset can be created with the script [organize_voice.py](organize_voice.py) that takes the following required parameters:

```bash
python3 organize_voice.py \
     --source=<directory of raw recordings> \
     --dest=<destination base directory> \
     --orig_name=<name of the original voice> \
     --dest_name=<new name of the voice> \
     --emotion-script=<emotion script used for the prompts> \
     --addenda-script=<special script used for addenda>
```
The parameters `--dest` and `--dest_name` together form the destination directory of the generated dataset. If you have multiple speaker recordings in one directory, each in its own subdirectory, you can simply change the parameters `--orig_name` and `--dest_name` to create the new dataset. The parameters `--emotion-script` and `--addenda-script` refer to the utterance scripts you used for recording the raw speaker data.

If you followed the naming conventions recommended in [Record dataset](README.md#record-dataset), you can combine multiple recording directories of the same speaker at once. The directory pattern that should be followed is: `<voice-name>_<emotion>/`, where `<emotion>` can be any style you want.

These optional parameters can be provided:

```bash
     --force                          overwrite destination directory if it exists
     --flac                           convert to flac instead of RIFF format
     --zero-emotion="neutral, ...."   add list of emotions where corresponding emotion level should be set to 0
     --verbose                        print some statistics at the end
```
By default, the original emotion values of the script given by `--emotion-script` are used for the emotion intensity level of each field inside the metadata file `index.tsv`. Recordings with emotion names starting with **addendum** are always set to emotion level `0`. By default, the emotion **neutral** is set to `0` as well, unless the parameter `--zero-emotion` is set differently.

For details about the final directory layout and the metadata format inside the generated `index.tsv` file, refer to [organize_voice.py](organize_voice.py).

## Run VAD (voice activity detection)

To create a JSON file containing detailed voice activity of all audio files of a directory, use the following script:

```bash
python3 vadiate.py <source directory of audio files> <output.json>
```

This will create a file with the following format:

```json
{
  "angry/h_angry_001.flac": {
    "overall": 4.779,
    "timestamps": [
      [
        0.45,
        2.302
      ],
      [
        2.53,
        4.318
      ]
    ],
    "begin": 0.45,
    "end": 4.318
  },
  ...
}
```

`overall` gives the total length of the recording, `timestamps` contains a list of all detected voice activities, `begin` and `end` mark the beginning and end of detected voice activity inside the recording. All times are given in seconds, accurate to the millisecond.

There might be warnings for **"No speech detected in ..."** which means the VAD couldn't recognize any valid speech. This happens in our experience foremost with very emotional recordings in combination with short utterances.

You can try the parameter `--use-dynamic-threshold` to automatically reduce the confidence threshold for the VAD prediction. Please always control the generated timings manually in those cases. Parameters of the VAD might also be needed to be tweaked according to your specific dataset. Refer to the documentation of [Silero VAD](https://github.com/snakers4/silero-vad) for the exact meaning of all parameters of the used Python API.

## Alignment

We used [MFA (Montreal Forced Aligner)](https://montreal-forced-aligner.readthedocs.io) to obtain phoneme-level alignments of the recordings.
In order to ensure reproducibility, [the official Docker image](https://hub.docker.com/r/mmcauliffe/montreal-forced-aligner) for MFA was used, which can be invoked by calling
```
alignment/run_docker.sh `pwd`/data/processed `pwd`/data/alignment
```
Note that in order to successfully run the script you need to first set up Docker, and then ensure that the user you are calling the script as has the required privileges. See [here](https://docs.docker.com/engine/install/linux-postinstall/) for more details.


Once the interactive docker container is running, you can perform the MFA alignment from scratch by running
```
cd /home/mfauser/data/scripts
./run_entire_pipeline.sh
```

This will write out alignments in TextGrid form under `data/alignment/alignment/` and write Grapheme-to-phoneme and acoustic models to `data/alignment/models`

Since the alignment files denote leading and trailing silences, they may be used in place of the VAD system to trim the audio.

## Acknowledgements
This project is part of the program Language Technology for Icelandic. The program was funded by the Icelandic Ministry of Culture and Business Affairs.
