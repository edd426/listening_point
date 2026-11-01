"""shorekit: the shore kit for The Listening Point.

Standard library only, integer arithmetic only, so every platform and every Python from 3.9 up
reaches the same verdict, the same footprint pixels and the same preview pixels.
"""

KIT_VERSION = "1.2.0"

# The limits the rules are written in (BUILD section 2 and the 2026-10-31 decisions).
MAX_LIVE = 48            # objects drawn at once; when this many are live and one more comes, a storm
STORM_TO = 40            # takes the oldest (with whatever rests on them) until at most this many remain
MAX_CELLS_SIDE = 64      # a bitmap is at most 64 x 64 cells
MAX_KEYS = 16            # palette keys, plus "." for transparent
MIN_OPAQUE = 16
MAX_OPAQUE = 2500
MAX_CHANNEL = 240        # no albedo channel above this
MAX_SCALE = 4            # pixels per cell side, 1-4 (look B: big enough to notice at desktop size)
MAX_LABEL = 8            # look B: at most a very short name
GLOW_MAX_PX = 64         # look B: the most frame pixels one object may light at night (one palette key)
FAINT_D = 48             # look C: an object's mean colour stands at least this far (redmean) from the ground
FAINT_RING = 6           #   around it, out to this many px past its box, at each of these conditions
FAINT_CONDITIONS = ("noon", "golden")
