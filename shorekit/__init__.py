"""shorekit: the shore kit for The Listening Point.

Standard library only, integer arithmetic only, so every platform and every Python from 3.9 up
reaches the same verdict, the same footprint pixels and the same preview pixels.
"""

KIT_VERSION = "1.0.0"

# The limits the rules are written in (BUILD section 2 and the 2026-10-31 decisions).
MAX_LIVE = 48            # objects drawn at once; a storm takes the oldest when room is needed
MAX_CELLS_SIDE = 64      # a bitmap is at most 64 x 64 cells
MAX_KEYS = 16            # palette keys, plus "." for transparent
MIN_OPAQUE = 16
MAX_OPAQUE = 2500
MAX_CHANNEL = 240        # no albedo channel above this
MAX_LABEL = 12
