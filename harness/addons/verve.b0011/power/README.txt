Power simulations and the no-op count for B-0011 (#53).

- power_fixed_k.py: the criterion as first relayed (fixed k = 0.52 envelopes).
- power_amended.py: the accepted amendment (per-start k envelope for reaction, k in [0, 1] for b).
  Both take one folder holding v02_table.csv (= ../table.csv) and vmap.csv (= docs/stock/driver_rows_benchmark_austria.csv).
- count_noop_ops.py <repo root>: ops whose value equals stock, which the build drops. 184 ops, 23 equal to stock,
  so every start must show 52 + 161 = 213 overwritten.
