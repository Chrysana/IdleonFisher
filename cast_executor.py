import time
from pynput.mouse import Button, Controller

_mouse = Controller()


def execute_cast(hold_ms: float, position: tuple[int, int] | None = None) -> None:
    """Simulate a fishing cast by holding left-click for hold_ms milliseconds.

    If position is given, the mouse is moved there before pressing.
    """
    if position is not None:
        _mouse.position = position
    _mouse.press(Button.left)
    time.sleep(hold_ms / 1000.0)
    _mouse.release(Button.left)
