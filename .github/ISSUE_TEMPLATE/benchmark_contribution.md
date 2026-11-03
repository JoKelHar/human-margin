---
name: Benchmark contribution
about: Propose a benchmark figure (CPM/CTR/CVR/CPA/ROAS/agency fee) with a source
title: "[benchmark] "
labels: benchmark, data
---

<!-- SPDX-License-Identifier: CC-BY-4.0 / Copyright 2026 João Harrison -->

Thank you for improving the benchmark library! Please read
[DATA_SOURCES.md](../DATA_SOURCES.md) first. Benchmark data is contributed under
**CC BY 4.0** and must be an **individual cited figure**, not a copy of a whole
table or dataset.

**The figure**

```yaml
- metric:            # cpm | ctr | cvr | cpa | roas | agency_fee
  industry:
  price_band:        # low | mid | high
  channel:           # meta | snapchat | tiktok | youtube | any
  geography:         # ISO country (NO, SE, …) or a region note
  value: { low: , point: , high: }   # a range, please, not a false point
  unit:              # ratio | nok | permille | multiplier
  source_name: ""
  source_url: ""
  published:         # YYYY-MM-DD
  quality:           # A (primary/measured) … D (rough assumption)
  notes: ""
```

**Checklist**

- [ ] This is a single cited figure, not a reproduction of a full table/dataset.
- [ ] The source is publicly available (not paywalled) and the URL works.
- [ ] The publication date is included and the figure is < 18 months old, or I
      have noted why an older figure is still useful.
- [ ] The number is real and from the cited source — not estimated or invented.
