"""Constants for the EmoSpeech Recorder application.

This module defines all constant values used throughout the application,
organized into logical groups for audio processing, user interface,
file handling, and keyboard bindings.
"""

class AudioConstants:
    """Audio processing related constants.

    Defines parameters for audio recording, processing, and analysis
    including FFT settings, mel spectrogram parameters, and normalization
    factors for different bit depths.
    """
    # Sample rates and channels
    DEFAULT_SAMPLE_RATE = 48000
    DEFAULT_CHANNELS = 1
    DEFAULT_BIT_DEPTH = 24
    SUPPORTED_BIT_DEPTHS = [16, 24]

    # FFT Parameters
    N_FFT = 2048
    HOP_LENGTH = 512

    # Mel Spectrogram
    N_MELS = 96  # Increased for better low frequency resolution
    FMIN = 50  # Hz - Lower bound for fundamental frequency
    FMAX = 12000  # Hz - Extended for better high frequency detail

    # Display ranges
    DB_MIN = -70  # Background noise level
    DB_MAX = -10  # Compressed range for better detail
    DB_REFERENCE = 1e-10  # Reference for dB calculation

    # Processing
    CLIPPING_THRESHOLD = 0.99  # 99% of maximum value
    AUDIO_CHUNK_SIZE = 1024
    MIN_CLIPPING_MARKER_DISTANCE = 5  # Frames between markers
    FREQUENCY_NOISE_FLOOR_DB = -50  # dB threshold for max frequency detection (-60 = more sensitive, -40 = less sensitive)

    # Normalization factors
    NORM_FACTOR_16BIT = 32768.0  # 2^15
    NORM_FACTOR_24BIT = 2147483648.0  # 2^31 (int32 for 24-bit)


class UIConstants:
    """User interface related constants.

    Defines visual appearance settings, timing parameters, layout ratios,
    and display configuration for the graphical user interface.
    """
    # Colors
    COLOR_BACKGROUND = 'black'
    COLOR_TEXT_NORMAL = 'green'
    COLOR_TEXT_RECORDING = 'red'
    COLOR_TEXT_INACTIVE = 'gray'
    COLOR_CLIPPING = 'red'
    COLOR_PLAYBACK_LINE = 'red'

    # Clipping display
    CLIPPING_LINE_WIDTH = 3
    CLIPPING_LINE_ALPHA = 0.7
    CLIPPING_WARNING_SYMBOL = '!'
    CLIPPING_WARNING_SIZE = 20
    CLIPPING_WARNING_POSITION = (0.02, 0.95)  # Relative position

    # Playback display
    PLAYBACK_LINE_WIDTH = 2
    PLAYBACK_LINE_ALPHA = 0.8

    # Timing (milliseconds)
    ANIMATION_UPDATE_MS = 20
    PLAYBACK_CHECK_MS = 50
    PLAYBACK_STOP_DELAY_MS = 50  # Delay after stopping playback
    FOCUS_DELAY_MS = 100
    POST_RECORDING_DELAY_MS = 500
    INITIAL_DISPLAY_DELAY_MS = 500  # Delay before showing initial recording
    STATUS_RESET_DELAY_MS = 1000

    # Process timing (seconds)
    AUDIO_PROCESS_SLEEP = 0.1
    PROCESS_JOIN_TIMEOUT = 0.1
    PLAYBACK_STOP_DELAY = 0.05  # Same as PLAYBACK_STOP_DELAY_MS but in seconds

    # Window layout ratios
    INFO_FRAME_HEIGHT_RATIO = 0.05
    CONTROL_FRAME_HEIGHT_RATIO = 0.20
    TEXT_WRAP_RATIO = 0.9
    DEFAULT_WINDOW_SIZE_RATIO = 0.8

    # Padding
    MAIN_FRAME_PADDING = 20
    FRAME_SPACING = 10

    # Font scaling
    FONT_SCALE_MEDIUM = 0.7
    FONT_SCALE_SMALL = 0.5
    MIN_FONT_SIZE_LARGE = 40
    MIN_FONT_SIZE_MEDIUM = 28
    MIN_FONT_SIZE_SMALL = 14

    # Spectrogram display
    SPECTROGRAM_WIDTH_INCHES = 8
    SPECTROGRAM_HEIGHT_INCHES = 2
    SPECTROGRAM_DPI = 100
    SPECTROGRAM_DISPLAY_SECONDS = 3.0

    # Axis settings
    AXIS_LABEL_FONTSIZE = 8
    AXIS_TICK_FONTSIZE = 6
    N_TIME_TICKS = 7
    N_FREQUENCY_TICKS = 8  # More ticks for better logarithmic display


class FileConstants:
    """File and path related constants.

    Defines default file paths, extensions, and audio format
    specifications for file operations.
    """
    DEFAULT_SCRIPT_FILE = 'utts.data'
    DEFAULT_RECORDING_DIR = 'recordings'
    AUDIO_FILE_EXTENSION = '.flac'
    LEGACY_AUDIO_FILE_EXTENSION = '.wav'
    NOT_FOUND_AUDIO = 'not_found.wav'

    # File formats
    PCM_16_SUBTYPE = 'PCM_16'
    PCM_24_SUBTYPE = 'PCM_24'
    FLAC_SUBTYPE = 'FLAC'


class KeyBindings:
    """Keyboard shortcuts.

    Defines all keyboard bindings for application control.
    Most keys use lowercase; special keys use Tkinter notation.
    """
    RECORD = 'space'
    PLAY = 'p'
    NAVIGATE_UP = 'Up'
    NAVIGATE_DOWN = 'Down'
    BROWSE_TAKES_LEFT = 'Left'
    BROWSE_TAKES_RIGHT = 'Right'
    TOGGLE_SPECTROGRAM = ['m', 'M']
    DELETE_RECORDING = 'd'
    QUIT = 'q'
    TOGGLE_FULLSCREEN = 'F10'
    SHOW_HELP = 'h'
    SHOW_INFO = 'i'


