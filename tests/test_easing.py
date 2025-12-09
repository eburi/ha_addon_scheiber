#!/usr/bin/env python3
"""
Tests for easing functions.
"""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scheiber" / "src"))

import pytest
import math
from easing import (
    linear,
    ease_in_sine,
    ease_out_sine,
    ease_in_out_sine,
    ease_in_quad,
    ease_out_quad,
    ease_in_out_quad,
    ease_in_cubic,
    ease_out_cubic,
    ease_in_out_cubic,
    ease_in_quart,
    ease_out_quart,
    ease_in_out_quart,
    get_easing_function,
    DEFAULT_EASING,
    EASING_FUNCTIONS,
)


class TestEasingFunctions:
    """Test all easing functions for correct behavior."""

    def test_linear(self):
        """Linear should return the same value."""
        assert linear(0.0) == 0.0
        assert linear(0.5) == 0.5
        assert linear(1.0) == 1.0

    def test_all_functions_start_at_zero(self):
        """All easing functions should start at 0.0."""
        for name, func in EASING_FUNCTIONS.items():
            result = func(0.0)
            assert result == pytest.approx(
                0.0, abs=1e-10
            ), f"{name} should start at 0.0"

    def test_all_functions_end_at_one(self):
        """All easing functions should end at 1.0."""
        for name, func in EASING_FUNCTIONS.items():
            result = func(1.0)
            assert result == pytest.approx(1.0, abs=1e-10), f"{name} should end at 1.0"

    def test_all_functions_monotonic(self):
        """All easing functions should be monotonically increasing."""
        steps = 100
        for name, func in EASING_FUNCTIONS.items():
            prev_value = 0.0
            for i in range(steps + 1):
                t = i / steps
                value = func(t)
                assert value >= prev_value, f"{name} should be monotonically increasing"
                prev_value = value

    def test_ease_in_out_sine_symmetry(self):
        """Ease in-out sine should be symmetric around 0.5."""
        func = ease_in_out_sine

        # Test symmetry: f(t) + f(1-t) should equal 1.0
        for i in range(1, 50):  # Skip 0 and 0.5 to avoid rounding issues
            t = i / 100
            result_left = func(t)
            result_right = func(1.0 - t)
            assert result_left + result_right == pytest.approx(
                1.0, abs=1e-10
            ), f"ease_in_out_sine should be symmetric at t={t}"

    def test_ease_in_slower_than_linear(self):
        """Ease-in functions should be slower than linear at the start."""
        for name in ["ease_in_sine", "ease_in_quad", "ease_in_cubic", "ease_in_quart"]:
            func = EASING_FUNCTIONS[name]
            # At 0.25 progress, ease-in should be less than linear
            assert func(0.25) < 0.25, f"{name} should be slower than linear at start"

    def test_ease_out_faster_than_linear(self):
        """Ease-out functions should be faster than linear at the start."""
        for name in [
            "ease_out_sine",
            "ease_out_quad",
            "ease_out_cubic",
            "ease_out_quart",
        ]:
            func = EASING_FUNCTIONS[name]
            # At 0.25 progress, ease-out should be more than linear
            assert func(0.25) > 0.25, f"{name} should be faster than linear at start"

    def test_get_easing_function_valid(self):
        """get_easing_function should return valid functions."""
        # Test with explicit name
        func = get_easing_function("linear")
        assert func == linear

        # Test with default (None)
        func = get_easing_function(None)
        assert func == EASING_FUNCTIONS[DEFAULT_EASING]

        # Test with default name
        func = get_easing_function()
        assert func == EASING_FUNCTIONS[DEFAULT_EASING]

    def test_get_easing_function_invalid(self):
        """get_easing_function should raise ValueError for invalid names."""
        with pytest.raises(ValueError, match="Unknown easing function"):
            get_easing_function("invalid_easing")

    def test_default_easing_is_ease_in_out_sine(self):
        """Default easing should be ease_in_out_sine."""
        assert DEFAULT_EASING == "ease_in_out_sine"

    def test_quad_cubic_quart_progression(self):
        """Higher order easing should be more extreme."""
        t = 0.5
        quad = ease_in_quad(t)
        cubic = ease_in_cubic(t)
        quart = ease_in_quart(t)

        # For ease-in at 0.5, higher orders should be smaller
        assert cubic < quad < t, "Cubic should be more extreme than quad"
        assert quart < cubic, "Quart should be more extreme than cubic"


class TestEasingRegistry:
    """Test the easing function registry."""

    def test_registry_contains_all_functions(self):
        """Registry should contain all expected easing functions."""
        expected_names = [
            "linear",
            "ease_in_sine",
            "ease_out_sine",
            "ease_in_out_sine",
            "ease_in_quad",
            "ease_out_quad",
            "ease_in_out_quad",
            "ease_in_cubic",
            "ease_out_cubic",
            "ease_in_out_cubic",
            "ease_in_quart",
            "ease_out_quart",
            "ease_in_out_quart",
        ]

        for name in expected_names:
            assert name in EASING_FUNCTIONS, f"Registry should contain {name}"

    def test_registry_functions_are_callable(self):
        """All functions in registry should be callable."""
        for name, func in EASING_FUNCTIONS.items():
            assert callable(func), f"{name} should be callable"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
