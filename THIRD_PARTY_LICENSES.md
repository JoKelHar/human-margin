<!--
SPDX-License-Identifier: CC-BY-4.0
Copyright 2026 João Harrison
-->
# Third-party licences

Human Margin is licensed under Apache-2.0 (code) and CC BY 4.0 (benchmark
library and docs). It depends on the third-party packages below. **All runtime
dependencies are permissive (MIT / BSD-3-Clause) and compatible with
Apache-2.0** — there are no copyleft (GPL / LGPL / AGPL) dependencies.

This list is maintained by hand; regenerate your own view at any time with:

```bash
uv run python - <<'PY'
import importlib.metadata as m
for d in m.distributions():
    md = d.metadata
    print(md["Name"], md["Version"], md.get("License") or
          next((c.split("::")[-1].strip() for c in md.get_all("Classifier", [])
                if c.startswith("License")), "?"))
PY
```

## Runtime dependencies

| Package | Licence | Compatible with Apache-2.0 |
|---------|---------|:--:|
| [DuckDB](https://github.com/duckdb/duckdb) | MIT | ✅ |
| [pandas](https://github.com/pandas-dev/pandas) | BSD-3-Clause | ✅ |
| [NumPy](https://github.com/numpy/numpy) | BSD-3-Clause | ✅ |
| [PyYAML](https://github.com/yaml/pyyaml) | MIT | ✅ |

## Optional dependencies

| Package | Extra | Licence | Compatible |
|---------|-------|---------|:--:|
| [Streamlit](https://github.com/streamlit/streamlit) | `dashboard` | Apache-2.0 | ✅ |
| [SciPy](https://github.com/scipy/scipy) | `modeling` | BSD-3-Clause | ✅ |
| [statsmodels](https://github.com/statsmodels/statsmodels) | `modeling` | BSD-3-Clause | ✅ |
| [PyMC](https://github.com/pymc-devs/pymc) | `modeling` | Apache-2.0 | ✅ |

## Development / build

| Package | Licence | Compatible |
|---------|---------|:--:|
| [pytest](https://github.com/pytest-dev/pytest) | MIT | ✅ |
| [Hatchling](https://github.com/pypa/hatch) | MIT | ✅ |

## Notes

- Transitive dependencies of the packages above carry their own licences; the
  ones that matter in practice (e.g. `python-dateutil` — Apache-2.0/BSD,
  `pytz` — MIT) are likewise permissive.
- If a future dependency introduces a copyleft or otherwise Apache-incompatible
  licence, it must be flagged in the pull request and an alternative proposed
  (see [CONTRIBUTING.md](CONTRIBUTING.md)).
- The full texts of the Apache-2.0 and CC BY 4.0 licences are in
  [`LICENSE`](LICENSE) and [`LICENSE-DATA`](LICENSE-DATA).
