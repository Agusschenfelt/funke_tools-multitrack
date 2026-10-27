"""Internal audio format. Audio is converted only on export."""

import numpy as np

SAMPLE_RATE = 44100
CHANNELS = 2
DTYPE = np.float32

# Longest accepted song. Enforced by the worker before decoding and mirrored by the web upload
# screen; 0.5 s of tolerance absorbs container rounding.
MAX_DURATION_SECONDS = 600
MAX_DURATION_TOLERANCE_SECONDS = 0.5
# Compressed stems the studio streams instead of the float WAVs. AAC-LC in .m4a decodes with
# decodeAudioData in every current browser (Opus/WebM does not on older Safari). The encoder
# starts with 1024 priming samples; the mp4 edit list trims them in decoders that honor it, the
# studio trims them itself otherwise. Every stem is encoded the same way, so previews stay aligned
# with each other either way.
PREVIEW_BITRATE_KBPS = 128
PREVIEW_PRIMING_SAMPLES = 1024
PREVIEW_EXTENSION = ".m4a"
