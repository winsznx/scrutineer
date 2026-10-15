"""Small, dependency-light statistics used by the metrics: z-test, bootstrap, kappa."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence


def two_proportion_ztest(success_a: int, n_a: int, success_b: int, n_b: int) -> tuple[float, float]:
    """Two-sided z-test for p_a != p_b with pooled variance. Returns (z, p_value)."""
    if n_a == 0 or n_b == 0:
        return float("nan"), float("nan")
    p_a, p_b = success_a / n_a, success_b / n_b
    pooled = (success_a + success_b) / (n_a + n_b)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    if se == 0:
        return float("nan"), float("nan")
    z = (p_a - p_b) / se
    return z, math.erfc(abs(z) / math.sqrt(2))


def wilson_interval(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


def bootstrap_mean_ci(
    values: Sequence[float], resamples: int = 1000, seed: int = 0, level: float = 0.95
) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of `values`."""
    if not values:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples))
    lo = means[int((1 - level) / 2 * resamples)]
    hi = means[min(resamples - 1, int((1 + level) / 2 * resamples))]
    return lo, hi


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    if len(a) != len(b) or not a:
        return float("nan")
    labels = sorted(set(a) | set(b))
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    expected = sum((a.count(label) / n) * (b.count(label) / n) for label in labels)
    if expected == 1:
        return 1.0 if observed == 1 else float("nan")
    return (observed - expected) / (1 - expected)
