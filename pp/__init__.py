"""Pixel Perfect — a headless, rule-driven pixel sprite forge."""
import warnings

# numpy 2.0 + Apple Accelerate emits spurious FP warnings from matmul.
warnings.filterwarnings("ignore", message=".*encountered in matmul", category=RuntimeWarning)
# depth buffers use +inf for empty pixels; inf - inf comparisons are intended to be False.
warnings.filterwarnings("ignore", message="invalid value encountered in subtract", category=RuntimeWarning)
