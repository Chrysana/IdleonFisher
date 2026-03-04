# Hold time constants for IdleOn fishing cast positions 0-7.
# Piecewise linear: two segments meeting at position 3.5 (MID).
#   MIN_HOLD_MS = hold time (ms) extrapolated to position 0
#   MID_HOLD_MS = hold time (ms) at position 3.5 (the midpoint)
#   MAX_HOLD_MS = hold time (ms) at position 7
MIN_HOLD_MS: float = 197.6
MID_HOLD_MS: float = 692.1
MAX_HOLD_MS: float = 938.7

_SPLIT: float = 3.5


def get_hold_time(position: float) -> float:
    """Return hold duration in milliseconds for a given cast position (0.0 – 7.0)."""
    position = max(0.0, min(7.0, position))
    if position <= _SPLIT:
        return MIN_HOLD_MS + (position / _SPLIT) * (MID_HOLD_MS - MIN_HOLD_MS)
    else:
        return MID_HOLD_MS + ((position - _SPLIT) / _SPLIT) * (MAX_HOLD_MS - MID_HOLD_MS)
