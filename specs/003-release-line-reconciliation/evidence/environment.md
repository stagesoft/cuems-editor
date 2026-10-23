# Environment (T002)

- Host: Debian 13 (Linux 6.12.111+deb13-amd64), pyenv 3.11.9.
- Venv `$S/venv`: `cuemsutils 0.1.1` installed from `git archive 4b336cd` of cuems-utils (the candidate tag, exported
  so no sibling repository is touched); pytest 9.1.1, pytest-cov 7.1.0, pytest-xdist 3.8.0, peewee 3.17.8,
  websockets 14.1. `ruff` is run through `uvx` (not in the venv).
- Venv `$S/venv2`: same, with cuemsutils from `git archive 387598e` (cuems-utils `feat/xml-refactor` head).
- `$S/cuems-utils` is a symlink to the exported tag, because `tests/test_config_round_trip.py` reads
  `../cuems-utils/tests/data/corpus/`. (For the head run the symlink still points at the tag corpus: indicative.)
- Run: `PYTHONPATH=src $S/venv/bin/python -m pytest -q -p no:cacheprovider`.

## Sibling checkouts change two results (found at T008)

`tests/test_upstream_gates.py::test_nodeconf_engine_callback_accepts_node_set` skips when `../cuems-nodeconf` is absent
(a scratch worktree) and **fails with the same `ModuleNotFoundError: No module named 'cuemsnodeconf.CuemsNodeConf'`
on `a2431f0` itself** when run in a directory beside the sibling checkout (measured by a temporary worktree beside the
siblings, removed afterwards). It is environmental and common to both arms. All arm comparisons therefore run in
scratch worktrees, where it skips.
