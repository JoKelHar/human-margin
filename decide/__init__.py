# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Decide: the budget-check calculator app.

Scenario in, three positions out (buying and creator modes). The maths lives in
:mod:`decide.compute`; the browser mirror is ``decide/web/budget-core.js`` and the
two are pinned together by the golden cases under ``decide/tests/golden`` and the
Node parity runner ``decide/build/parity_node.js``. Shared planner primitives
(cost bands, the prescriptive copy guard, ``repo_root``) stay in ``mediekjop``.
"""

from __future__ import annotations
