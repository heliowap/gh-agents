---
name: tdd
description: "Test-driven development. Use when building features or fixing bugs where a testable seam exists."
---

Red, then green, then refactor — one slice at a time.

1. Pick one seam (a public function, a CLI contract, an endpoint).
2. Write the smallest test that would fail without the change. Run it; see it
   fail for the right reason.
3. Write the minimal implementation that turns it green. Run it.
4. Refactor only while green. Repeat for the next slice.

Expected values come from an independent source of truth — never recompute
them the way the code does. A fix ships with the test that fails without it.
