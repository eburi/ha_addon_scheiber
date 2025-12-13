"""
Easing functions for smooth brightness transitions.

Based on easings.net and Ashley's Light Fader implementation.
All functions take a progress value (0.0 to 1.0) and return an eased value (0.0 to 1.0).
"""

import math


def linear(t: float) -> float:
    """
    Linear easing - no acceleration or deceleration.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    return t


def ease_in_sine(t: float) -> float:
    """
    Sine easing in - slow start, accelerating.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    return 1 - math.cos((t * math.pi) / 2)


def ease_out_sine(t: float) -> float:
    """
    Sine easing out - fast start, decelerating.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    return math.sin((t * math.pi) / 2)


def ease_in_out_sine(t: float) -> float:
    """
    Sine easing in-out - slow start and end, faster in middle.
    This is the default easing function for natural-looking transitions.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    return -(math.cos(math.pi * t) - 1) / 2


def ease_in_quad(t: float) -> float:
    """
    Quadratic easing in - slow start, accelerating.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    return t * t


def ease_out_quad(t: float) -> float:
    """
    Quadratic easing out - fast start, decelerating.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    return 1 - (1 - t) * (1 - t)


def ease_in_out_quad(t: float) -> float:
    """
    Quadratic easing in-out - slow start and end, faster in middle.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    if t < 0.5:
        return 2 * t * t
    else:
        return 1 - math.pow(-2 * t + 2, 2) / 2


def ease_in_cubic(t: float) -> float:
    """
    Cubic easing in - slow start, strong acceleration.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    return t * t * t


def ease_out_cubic(t: float) -> float:
    """
    Cubic easing out - fast start, strong deceleration.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    return 1 - math.pow(1 - t, 3)


def ease_in_out_cubic(t: float) -> float:
    """
    Cubic easing in-out - slow start and end, much faster in middle.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - math.pow(-2 * t + 2, 3) / 2


def ease_in_quart(t: float) -> float:
    """
    Quartic easing in - very slow start, very strong acceleration.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    return t * t * t * t


def ease_out_quart(t: float) -> float:
    """
    Quartic easing out - very fast start, very strong deceleration.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    return 1 - math.pow(1 - t, 4)


def ease_in_out_quart(t: float) -> float:
    """
    Quartic easing in-out - very slow start and end, extremely fast in middle.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased value from 0.0 to 1.0
    """
    if t < 0.5:
        return 8 * t * t * t * t
    else:
        return 1 - math.pow(-2 * t + 2, 4) / 2


# Easing function registry - maps string names to functions
EASING_FUNCTIONS = {
    "linear": linear,
    "ease_in_sine": ease_in_sine,
    "ease_out_sine": ease_out_sine,
    "ease_in_out_sine": ease_in_out_sine,
    "ease_in_quad": ease_in_quad,
    "ease_out_quad": ease_out_quad,
    "ease_in_out_quad": ease_in_out_quad,
    "ease_in_cubic": ease_in_cubic,
    "ease_out_cubic": ease_out_cubic,
    "ease_in_out_cubic": ease_in_out_cubic,
    "ease_in_quart": ease_in_quart,
    "ease_out_quart": ease_out_quart,
    "ease_in_out_quart": ease_in_out_quart,
}

# Default easing function
DEFAULT_EASING = "ease_in_out_sine"


def get_easing_function(name: str = None):
    """
    Get an easing function by name.

    Args:
        name: Name of the easing function (e.g., "ease_in_out_sine")
              If None, returns the default easing function.

    Returns:
        The easing function

    Raises:
        ValueError: If the easing function name is not recognized
    """
    if name is None:
        name = DEFAULT_EASING

    if name not in EASING_FUNCTIONS:
        raise ValueError(
            f"Unknown easing function: {name}. "
            f"Available: {', '.join(EASING_FUNCTIONS.keys())}"
        )

    return EASING_FUNCTIONS[name]
