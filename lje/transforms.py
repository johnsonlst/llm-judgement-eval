"""Prompt transforms used as experimental arms.

Each transform takes (prompt, seed) and returns a new prompt. They must change
only what they claim to change, so any verdict flip is attributable to it.
"""
import random


def identity(prompt: str, seed: int) -> str:
    return prompt


def shuffle_list(prompt: str, seed: int, marker: str = "- ") -> str:
    """Permute the lines that start with `marker` (e.g. a headline list).

    Lines keep their slots, so surrounding instructions are untouched. A seeded
    RNG makes each (item, rep) reproducible; the order is guaranteed to change
    when there are at least two distinct list lines.
    """
    lines = prompt.split("\n")
    idx = [i for i, l in enumerate(lines) if l.startswith(marker)]
    block = [lines[i] for i in idx]
    if len(set(block)) < 2:
        return prompt
    rng = random.Random(seed)
    perm = block[:]
    while perm == block:
        rng.shuffle(perm)
    for i, l in zip(idx, perm):
        lines[i] = l
    return "\n".join(lines)


TRANSFORMS = {"orig": identity, "shuffle": shuffle_list}
