"""Internal audio format. Audio is converted only on export."""

import numpy as np

SAMPLE_RATE = 44100
CHANNELS = 2
DTYPE = np.float32

# Longest accepted song. Enforced by the worker before decoding and mirrored by the web upload
# screen; 0.5 s of tolerance absorbs container rounding.
MAX_DURATION_SECONDS = 600
MAX_DURATION_TOLERANCE_SECONDS = 0.5
