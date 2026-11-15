# Ruling B test: seed verve-test's launcher store, then one stock direct start (2026-11-15 02:48 PT)

- verve-test's store was seeded from the registered fixture's 4 files (store_seed.txt: names and hashes).
- **Result: FAIL.** The run's test copy (test-shell-20261115-104857) still got Tyler's Steam save imported:
  "copied the Steam save (2 file(s), 778984 bytes) into the launcher saves of profile test-shell-...". A test copy
  doesn't inherit verve-test's store, so Swofty imports into each new copy regardless.
- Ruling A's cleanup handled it: the copy was verified sha256-identical to the Steam files and deleted, along with its
  career-vault folder (cleanup.txt). Saves unchanged (32 entries); post-run CLEAN.
- verve-test's seeded store (4 fixture files) is still in place, pending a ruling on whether to keep it.
- **Second direct-start race:** the early safety car recurred almost to the second (SCAR deployed at 3.18 s vs the
  pilot's 3.13 s; returning 142.95 s vs 143.31 s; resume 189.13 s vs 189.48 s). The AI player car was again
  disqualified on lap 5 (infringement 19). Difficulty read 19. The direct start's safety car looks deterministic,
  driven by a setting, not random.
