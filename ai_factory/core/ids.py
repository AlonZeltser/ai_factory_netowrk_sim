from __future__ import annotations

import random
from dataclasses import dataclass

import xxhash


@dataclass
class IdGenerator:
    """Deterministic ID generator.

    We use randomness (seeded) to create stable-but-nontrivial IDs so that:
      * tests can assert determinism
      * different jobs in the same simulation don't collide
    """

    seed: int

    def __post_init__(self) -> None:
        self._rnd = random.Random(self.seed)

    def next_int(self, *, bits: int) -> int:
        # 31 bits fits comfortably in signed int ranges and is plenty for IDs.
        return self._rnd.getrandbits(bits)

    def child(self, salt: int | str) -> "IdGenerator":
        # Derive a new generator deterministically. Built-in hash() of a str changes per process,
        # so use xxhash on bytes (newer xxhash versions reject str).
        key = f"{self.seed}/{salt}".encode("utf-8")
        return IdGenerator(seed=xxhash.xxh64(key).intdigest() & 0x7FFFFFFF)

