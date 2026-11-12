"""Small, dependency-free statistics for label agreement."""
import math
import random
from collections import Counter


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion k/n."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def cohen_kappa(a: list, b: list) -> float:
    """Chance-corrected agreement between two label sequences."""
    n = len(a)
    if n == 0 or n != len(b):
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[v] * cb[v] for v in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def perm_test_mean(signal: list[float], returns: list[float], n_perm: int = 10000,
                   seed: int = 0) -> tuple[float, float]:
    """Mean of signal*return and a two-sided permutation p-value (shuffling signal).

    signal is typically +1 / 0 / -1 (bullish / neutral / bearish).
    """
    obs = sum(s * r for s, r in zip(signal, returns)) / len(signal)
    rng = random.Random(seed)
    s = list(signal)
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(s)
        if abs(sum(x * r for x, r in zip(s, returns)) / len(s)) >= abs(obs):
            hits += 1
    return obs, (hits + 1) / (n_perm + 1)


def bootstrap_ci(values: list[float], n_boot: int = 10000, alpha: float = 0.05,
                 seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean."""
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(n_boot))
    return means[int(alpha / 2 * n_boot)], means[int((1 - alpha / 2) * n_boot) - 1]
