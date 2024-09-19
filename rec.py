import argparse
import os
import queue
import sys
import tkinter as tk
from collections import defaultdict
from multiprocessing import Process, Value
from pathlib import Path
from time import sleep

import sounddevice as sd
import soundfile as sf


def parse_args():
    parser = argparse.ArgumentParser(
        description="Graphical interface for recording utterances from a script",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    io = parser.add_argument_group('input/output files')
    io.add_argument('--script', type=str, default='utts.data', help='recording script in Festival data format')
    io.add_argument('--recdir', type=str, default='recordings', help='output directory for recorded audio files')

    audio = parser.add_argument_group('audio configuration')
    audio.add_argument('--show-devices', action='store_true', help='show available audio devices and exit')
    audio.add_argument('--audio-device', type=str, help='audio device name')
    audio.add_argument('--audio-in', type=str, default=None, help='input device index or name')
    audio.add_argument('--audio-out', type=str, default=None, help='output device index or name')
    audio.add_argument('--channels', type=int, default=1, help='n channels to record: 1 for mono, 2 for stereo')
    audio.add_argument('--sr', type=int, default=44100, help='sampling rate to record')
    audio.add_argument('--bits', type=int, choices=[16, 24], default=16, help='bit depth, default=16, can be set to 24')
    audio.add_argument('--start-idx', type=int, default=0, help='starting index (not id) of UI')

    return parser.parse_args()


def key(event):
    global i, play
    code = event.keysym
    i_mp.value = i

    if code == 'space':
        # Record/stop recording
        if record.value == 0:
            record.value = 1
        else:
            record.value = 0
        l.config(fg="green" if not record.value else "red")
        p.join(0)
    elif code == 'p':
        # Play/pause
        play.value = 1
        p.join(0)
        set_colour = lambda c: l.config(fg=c)
        set_colour("yellow")
        frame.after(1000, lambda: set_colour("green"))
    elif code == 'Up':
        # Previous prompt
        if i <= 0:
            i = -1
            text.set("This was the first sentence! Go forward instead!")
        else:
            i -= 1
            text.set("{}".format(utts[i]))
            label.set("{}".format(labels[i]))
    elif code == 'Down':
        # Next prompt
        if i == len(utts) - 1:
            i = len(utts)
            text.set("End of list already reached! Go back :)")
            if record.value:
                record.value = 0
                p.join(0)
                l.config(fg="green")
        else:
            i += 1
            text.set("{}".format(utts[i]))
            label.set("{}".format(labels[i]))
            if record.value:
                i_mp.value = i
                record.value = 0
                p.join(0.01)
                record.value = 1
                p.join(0)
    elif code == 'q':
        # Quit
        p.terminate()
        root.destroy()


def audio_process(labels, recdir, takes, play, record, sr, channels, audio_in, i, bits):
    while True:
        if record.value:
            rec(labels[i.value], recdir, takes, record, sr, channels, audio_in, bits)
        if play.value:
            playback(labels[i.value], recdir, takes)
            play.value = 0
        sleep(0.1)


def playback(name, recdir, takes):
    wav_file = recdir / "{}_{}.wav".format(name, takes[name])
    if not wav_file.is_file():
        wav_file = "not_found.wav"
    print("Playback", wav_file)
    data, sr = sf.read(str(wav_file))
    sd.play(data, sr)


def rec(name, recdir, takes, record, sr, channels, audio_in, bits):
    q = queue.Queue()

    def callback(indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            print(status, file=sys.stderr)
        q.put(indata.copy())

    takes[name] += 1
    wav_file = str(recdir / "{}_{}.wav".format(name, takes[name]))
    print("Recording", wav_file)
    # Make sure the file is opened before recording anything:
    dtype, subtype = bits2dtype(bits)
    with sf.SoundFile(wav_file, mode='w', samplerate=sr, channels=channels,
                      subtype=subtype) as file:
        with sd.InputStream(samplerate=sr, device=audio_in, channels=channels,
                            callback=callback, dtype=dtype):
            while record.value:
                file.write(q.get())


def bits2dtype(bits):
    if bits == 24:
        subtype = 'PCM_24'
        dtype = 'int32'
    else:
        subtype = 'PCM_16'
        dtype = 'int16'
    return dtype, subtype


def test_recording(sr, channels, bits, audio_in, audio_in_device):
    q = queue.Queue()
    dtype, _ = bits2dtype(bits)

    def callback(indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        q.put(indata.copy())

    try:
        with sd.InputStream(samplerate=sr, dtype=dtype, device=audio_in, channels=channels,
                            callback=callback):
            for _ in range(10):  # only record for a short period
                q.get()
    except Exception as e:
        print(f"Recording not possible via {audio_in_device}: {e}")
        sys.exit(1)


def find_device_indices(device_name_or_index, kind):
    if device_name_or_index.isdigit():
        return int(device_name_or_index)
    else:
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if device['name'] == device_name_or_index:
                if (kind == 'input' and not device['max_input_channels']) or \
                        (kind == 'output' and not device['max_output_channels']):
                    # it might be the wrong kind of input/output device, try next
                    continue
                return i
        raise ValueError(f"Device '{device_name_or_index}' not found")


if __name__ == "__main__":
    args = parse_args()

    if args.show_devices:
        print(sd.query_devices())
        sys.exit()

    if args.audio_device:
        args.audio_in = args.audio_device
        args.audio_out = args.audio_device
        audio_in_idx = find_device_indices(args.audio_device, 'input')
        audio_out_idx = find_device_indices(args.audio_device, 'output')
    else:
        if args.audio_in is None or args.audio_out is None:
            print("No audio device specified. Available devices are:")
            print(sd.query_devices())
            sys.exit(1)
        else:
            audio_in_idx = find_device_indices(args.audio_in, 'input')
            audio_out_idx = find_device_indices(args.audio_out, 'output')

    sd.default.device = [audio_in_idx, audio_out_idx]
    sd.default.samplerate = args.sr

    recdir = Path(args.recdir)
    if os.path.exists(recdir):
        print(f"Warning: The directory {args.recdir} already exists.")
        confirmation = input("Do you want to continue? (y/n): ")
        if confirmation.lower() != "y":
            print("Exiting the program.")
            sys.exit()
    recdir.mkdir(exist_ok=True)

    # verify settings by starting a test recording ...
    test_recording(args.sr, args.channels, args.bits, audio_in_idx, args.audio_in)

    with open(args.script) as f:
        script = [i.strip('( )"\n').split(' "') for i in f.readlines()]
    labels, utts = zip(*script)
    takes = defaultdict(int)
    for i in labels:
        while (recdir / "{}_{}.wav".format(i, takes[i] + 1)).is_file():
            takes[i] += 1

    i = 0
    if args.start_idx:
        i=args.start_idx
    i_mp = Value('i', i)
    record = Value('i', 0)
    play = Value('i', 0)

    root = tk.Tk()
    text = tk.StringVar()
    label = tk.StringVar()
    text.set("{}".format(utts[i]))
    label.set("{}:".format(labels[i]))

    p = Process(target=audio_process, args=(
                labels, recdir, takes, play, record, args.sr, args.channels, audio_in_idx, i_mp, args.bits))
    p.daemon = True
    p.start()

    frame = tk.Frame(root, width=1200, height=900)
    frame.bind("<Key>", key)
    frame.pack()
    frame.focus_set()

    ll = tk.Label(textvariable=label, fg="green", font=("Helvetica", 60),
                  anchor="sw", justify="left")
    # TODO Make wraplength some function of window size and adjust placement accordingly in the future
    l = tk.Label(textvariable=text, fg="green", font=("Helvetica", 60),
                 anchor="center", justify="center", wraplength=1100)
    ll.place(y=0)
    l.place(rely=0.1, relx=0.2)

    root.mainloop()
