## 2025-05-15 - [Pathlib vs String Slicing Performance]
**Learning:** `pathlib.Path.relative_to` is approximately 100x slower than simple string slicing when calculating relative paths in large loops. Additionally, `pathlib.Path.rglob` traversal order is OS-dependent and non-deterministic.
**Action:** Use string slicing for relative path derivation in hot loops. Always sort file lists before building name-based indices (like Obsidian's stem resolution) to ensure environment-independent determinism.
