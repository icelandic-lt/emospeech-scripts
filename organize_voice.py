# This Python script reorganizes raw recording files of a voice recording to a new dataset structure.
# The destination raw recording of an emotional speech dataset is made up of multiple directories. Each directory
# contains recordings of either 6 distinct emotions or one of 2 addenda recordings for spelling out numbers and letters
# in 2 different neutral styles.
# Additionally, for each voice a recording prompt script is provided with id, intensity level and text. For the addenda
# no intensity level is used.
#
# The target directory layout is as follows:
#
#  voice-name /
#    |
#    +--addendum1/
#    |        |
#    |        +--voice-name_addendum1_001.wav
#    |        +--voice-name_addendum1_002.wav
#    |        | ...
#    |        +--voice-name_addendum1_N.wav
#    +--addendum2/
#    |        ..
#    +--emotion1(angry, happy, ...)/
#    |        |
#    |        +--voice-name_emotion1_001.wav
#    |        +--voice-name_emotion1_002.wav
#    |        | ...
#    |        +--voice-name_emotion1_N.wav
#    +--emotion2/
#    |        ..
#    +--emotionN/
#    |
#    + index.tsv
#
# The file index.tsv structure is as follows:
#
#       <relative_path_to_audio_file> \t <voice-name> \t  <utterance text> \t <emotion> \t <Intensity level 1-5>
#
# The structure of the source files directory is as follows:
#
#  data_directory /
#    |
#    +--voice-name_emotion1/*.wav
#    |        |
#    |        +--t3_unique-id-1_1.wav
#    |        +--t3_unique-id-1_2.wav
#    |        +--t3_unique-id-2_1.wav
#    |        | ...
#    |        +--t3_unique-id-N_M.wav
#    +--voice-name_emotion2/*.wav
#       ...
# The single unique-id fields of the filename correspond to the meta-data's file unique id of the related utterance. Each
# of these files is furthermore indexed with a counter _1, _2, _3, etc. for each recording try of the utterance. Only
# the file with the highest counter value should be picked if there are multiple tries of an utterance. The prefix t3_
# stands for "Talrómur3". The unique id is always 0 numbers with leading zeros. These are not necessarily monotonically
# increasing and can "jump" as they have been selected from another utterance corpus. The filenames can also contain
# spaces, mainly in front of the suffix ".wav".
#
# The raw material emotion script has the following structure, one utterance per row:
#
#       ( t3_<unique-id-per-folder>  "<Intensity level 1-5>: <utterance text>" )
#
# The addenda script has the following structure, one utterance per row:
#
#       ( t3a_<unique-id-per-folder> "<utterance text>" )
#
# Whereas the source directory unique-id's are non-monotonic, the destination unique-id's are always monotonically increasing numbers
# and start with 001. The source directory unique-id's are only unique per folder.0

import argparse
from collections import Counter
import os
import shutil
import re
import soundfile as sf
from tqdm import tqdm

def parse_arguments():
    parser = argparse.ArgumentParser(description="Organize voice recordings")
    parser.add_argument("--orig_name", required=True, help="Original name of the voice")
    parser.add_argument("--dest_name", required=True, help="New name of the voice")
    parser.add_argument("--source", required=True, help="Source directory")
    parser.add_argument("--dest", required=True, help="Destination directory")
    parser.add_argument("--emotion-script", required=True, help="Utterance script for emotion recordings")
    parser.add_argument("--addenda-script", required=True, help="Utterance script for addenda recordings")
    parser.add_argument("--verbose", action="store_true", help="Display detailed statistics at the end")
    parser.add_argument("--force", action="store_true", help="Overwrite destination directory without prompting")
    parser.add_argument("--zero-emotion", help="Comma-separated list of emotions to set intensity to 0")
    parser.add_argument("--flac", action="store_true", help="Convert audio files to FLAC format")
    return parser.parse_args()


def read_script(script_path, is_emotion=True):
    script_data = {}
    with open(script_path, 'r', encoding='utf-8') as f:
        for line in f:
            match = re.match(r'\(\s*(t3a?_\d+)\s*"(.*?)"\s*\)', line.strip())
            if match:
                uid, text = match.groups()
                if is_emotion:
                    intensity, utterance = text.split(':', 1)
                    script_data[uid] = (intensity.strip(), utterance.strip())
                else:
                    script_data[uid] = text.strip()
    return script_data

def get_emotions_and_addenda(source_dir, orig_name):
    emotions = []
    addenda = []
    for subdir in os.listdir(source_dir):
        if subdir.startswith(orig_name):
            _, emotion = subdir.split('_', 1)
            if emotion.startswith('addendum'):
                addenda.append(emotion)
            else:
                emotions.append(emotion)
    return emotions, addenda

def create_directory_structure(dest_dir, emotions, addenda):
    for emotion in emotions + addenda:
        os.makedirs(os.path.join(dest_dir, emotion), exist_ok=True)

def process_files(source_dir, dest_dir, orig_name, dest_name, emotion_script, addenda_script, addenda, zero_emotions, use_flac):
    index_data = []
    file_counts = Counter()

    total_files = sum(len([f for f in os.listdir(os.path.join(source_dir, subdir)) if f.endswith('.wav')])
                      for subdir in os.listdir(source_dir) if subdir.startswith(orig_name))

    pbar = tqdm(total=total_files, desc="Processing files", unit="file")

    for subdir in os.listdir(source_dir):
        if not subdir.startswith(orig_name):
            continue

        _, emotion = subdir.split('_', 1)
        is_addendum = emotion in addenda
        script = addenda_script if is_addendum else emotion_script

        src_subdir = os.path.join(source_dir, subdir)
        files = [f for f in os.listdir(src_subdir) if f.endswith('.wav')]

        utterance_files = {}
        for file in files:
            match = re.match(r'(t3a?_\d+)_(\d+)\.wav', file.replace(' ', ''))
            if match:
                base_name, counter = match.groups()
                if base_name not in utterance_files or int(counter) > int(utterance_files[base_name][1]):
                    utterance_files[base_name] = (file, counter)

        file_counter = 1
        for base_name, (file, _) in sorted(utterance_files.items()):
            src_path = os.path.join(src_subdir, file)

            if is_addendum:
                dest_subdir = emotion
                intensity = '0'
                utterance = script.get(f'{base_name}', '')
            else:
                dest_subdir = emotion
                intensity, utterance = script.get(f'{base_name}', ('', ''))
                if emotion in zero_emotions:
                    intensity = '0'

            new_file_name = f'{dest_name}_{emotion}_{file_counter:03d}.{"flac" if use_flac else "wav"}'
            dest_path = os.path.join(dest_dir, dest_subdir, new_file_name)

            if use_flac:
                # we need to find the correct bit depth of the source file
                with sf.SoundFile(src_path) as src_file:
                    original_subtype = src_file.subtype
                    original_format = src_file.format

                    if original_subtype in ['PCM_16', 'PCM_U8']:
                        np_dtype = 'int16'
                    elif original_subtype in ['PCM_24', 'PCM_32']:
                        np_dtype = 'int32'
                    elif original_subtype == 'FLOAT':
                        np_dtype = 'float32'
                    else:
                        np_dtype = 'float32'  # Fallback

                    # read audio data with correct dtype
                    data = src_file.read(dtype=np_dtype)
                    samplerate = src_file.samplerate

                # convert to FLAC with original bit-depth and dtype
                sf.write(dest_path, data, samplerate, format='FLAC', subtype=original_subtype)
            else:
                shutil.copy2(src_path, dest_path)

            relative_path = new_file_name
            index_data.append(f'{relative_path}\t{dest_name}\t{dest_subdir}\t{intensity}\t{utterance}\n')

            file_counter += 1
            file_counts[dest_subdir] += 1

            pbar.update(1)

    pbar.close()

    return index_data, file_counts


def write_index_file(dest_dir, index_data):
    index_path = os.path.join(dest_dir, 'index.tsv')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.writelines(index_data)

def main():
    args = parse_arguments()

    if os.path.exists(args.dest):
        if args.force:
            shutil.rmtree(args.dest)
        else:
            overwrite = input(f"Destination directory '{args.dest}' already exists. Overwrite? (y/n): ").lower()
            if overwrite != 'y':
                print("Operation aborted.")
                return
            shutil.rmtree(args.dest)

    os.makedirs(args.dest)

    emotion_script = read_script(args.emotion_script, is_emotion=True)
    addenda_script = read_script(args.addenda_script, is_emotion=False)

    emotions, addenda = get_emotions_and_addenda(args.source, args.orig_name)
    create_directory_structure(args.dest, emotions, addenda)

    zero_emotions = args.zero_emotion.split(',') if args.zero_emotion else []
    index_data, file_counts = process_files(args.source, args.dest, args.orig_name, args.dest_name, emotion_script, addenda_script, addenda, zero_emotions, args.flac)
    write_index_file(args.dest, index_data)

    print(f"Voice recordings organized successfully. Output directory: {args.dest}")

    if args.verbose:
        print("\nFile counts per emotion/addendum:")
        for emotion, count in file_counts.items():
            print(f"{emotion}: {count}")

if __name__ == "__main__":
    main()