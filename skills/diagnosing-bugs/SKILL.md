---
name: diagnosing-bugs
description: "Diagnosis loop for bugs and regressions. Use when something is reported broken, throwing, or behaving unexpectedly — before proposing fixes."
---

Diagnose before fixing. A fix without a reproduced root cause is a guess.

1. Reproduce reliably — the smallest input or command that shows the bug.
2. Trace the path from entry point to failure; find where expected and actual
   diverge. Add targeted logging only if tracing stalls.
3. Name the root cause in one sentence before touching code.
4. Fix the cause, not the symptom. Add the regression test that fails without
   the fix (`tdd`).
5. Verify the fix kills the reproduction, not just the test.
