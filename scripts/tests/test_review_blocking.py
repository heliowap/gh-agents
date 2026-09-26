"""Seam: the module's public functions + the CLI contract the workflow parses."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review_blocking import blocking_count, latest_review

SCRIPT = Path(__file__).resolve().parents[1] / "review_blocking.py"


def _comment(login, body, created="2026-09-24T10:00:00Z", url="https://example/c/1"):
    return {"user": {"login": login}, "body": body, "created_at": created, "html_url": url}


def test_blocking_count_reads_summary():
    assert blocking_count("BLOCKING\n- x\nSUMMARY: 2 BLOCKING, 1 WARNING, 0 NIT") == 2


def test_blocking_count_none_without_summary():
    assert blocking_count("looks fine") is None


def test_latest_review_picks_latest_bot_comment_with_summary():
    older = _comment("github-actions[bot]", "SUMMARY: 3 BLOCKING, 0 WARNING, 0 NIT",
                     created="2026-09-24T09:00:00Z")
    newer = _comment("github-actions[bot]", "SUMMARY: 0 BLOCKING, 0 WARNING, 0 NIT",
                     created="2026-09-24T11:00:00Z")
    human = _comment("heliowap", "SUMMARY: 9 BLOCKING, 0 WARNING, 0 NIT",
                     created="2026-09-24T12:00:00Z")
    assert latest_review([newer, human, older]) is newer


def test_latest_review_empty():
    assert latest_review([]) is None
    assert latest_review([_comment("heliowap", "hi")]) is None


def test_cli_comments_outputs_url_and_block():
    body = "BLOCKING\n- foo.py:10 bad\n\nWARNING\n  (nenhum)\n\nSUMMARY: 1 BLOCKING, 0 WARNING, 0 NIT"
    comments = json.dumps([_comment("github-actions[bot]", body, url="https://example/c/9")])
    out = subprocess.run([sys.executable, str(SCRIPT), "--comments"],
                         input=comments, capture_output=True, text=True, check=False)
    assert out.returncode == 0
    data = json.loads(out.stdout)
    assert data["blocking"] == 1 and data["url"] == "https://example/c/9"
    assert "foo.py:10" in data["block"]


def test_cli_missing_summary_exits_zero_with_warning():
    out = subprocess.run([sys.executable, str(SCRIPT)],
                         input="no summary here", capture_output=True, text=True, check=False)
    assert out.returncode == 0
    assert json.loads(out.stdout)["blocking"] == 0
    assert "SUMMARY" in out.stderr


def _cli(comments, *args):
    out = subprocess.run([sys.executable, str(SCRIPT), "--comments", *args],
                         input=json.dumps(comments), capture_output=True, text=True,
                         check=False)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_cli_since_ignores_valid_review_from_before_the_run():
    # intrador #1415: this run's review came out off-format; without the cutoff
    # the step fell back to the previous SHA's review and reported its count.
    previous = _comment("github-actions[bot]", "SUMMARY: 2 BLOCKING, 0 WARNING, 0 NIT",
                        created="2026-09-13T20:02:20Z", url="https://example/previous-sha")
    current = _comment("github-actions[bot]", "SUMMARY: the 2 earlier BLOCKINGs are fixed",
                       created="2026-09-13T20:43:14Z", url="https://example/current")
    data = _cli([previous, current], "--since", "2026-09-13T20:30:00Z")
    assert data == {"blocking": 0, "block": "", "url": "", "summary": "missing"}


def test_cli_since_keeps_the_review_of_this_run():
    body = "BLOCKING\n- a.py:1 bad\n\nSUMMARY: 1 BLOCKING, 0 WARNING, 0 NIT"
    current = _comment("github-actions[bot]", body, created="2026-09-13T20:43:14Z",
                       url="https://example/current")
    data = _cli([current], "--since", "2026-09-13T20:30:00Z")
    assert data["blocking"] == 1 and data["url"] == "https://example/current"
    assert data["summary"] == "ok"


def test_cli_accepts_marked_summary_from_current_review():
    # All-Medical #498: the review is complete, but the final label is bold.
    body = "BLOCKING\n  (none)\n\n**SUMMARY: 0 BLOCKING, 2 WARNING, 7 NIT**"
    review = _comment("github-actions[bot]", body, url="https://example/current")
    assert _cli([review]) == {
        "blocking": 0, "block": "", "url": "https://example/current", "summary": "ok"
    }


def test_marked_summary_ends_the_block():
    body = (
        "BLOCKING\n  a.py:1: real\n\n"
        "**SUMMARY:** 1 BLOCKING, 0 WARNING, 0 NIT\n"
        "RECOMMEND: fix before merge\n"
    )
    out = subprocess.run([sys.executable, str(SCRIPT)], input=body,
                         capture_output=True, text=True, check=False)
    assert out.returncode == 0
    assert json.loads(out.stdout) == {"blocking": 1, "block": "  a.py:1: real"}


def test_translated_summary_selects_review():
    # Reviews may translate the severity labels along with the summary label.
    for closing in (
        "RESUMO: 0 BLOQUEIOS, 3 AVISOS, 2 PEQUENOS",
        "SUMÁRIO: 0 BLOQUEIOS, 1 AVISO, 2 PEQUENAS OBSERVAÇÕES",
        "SUMÁRIO: 0 BLOQUEIO, 0 AVISO, 3 PEQUENAS OBSERVAÇÕES",
    ):
        review = _comment("github-actions[bot]", "BLOQUEIO\n  (nenhum)\n\n" + closing)
        assert _cli([review])["summary"] == "ok", closing


def test_pr_23_heading_keeps_blocking_detail_out_of_empty_issue_body():
    # gh-agents PR #23: issue #27 currently has an empty BLOCKING code block.
    body = (
        "Review complete. Findings below.\n"
        "## BLOCKING\n"
        "- `.github/workflows/dogfood.yml:23` — check the workflow filter.\n"
        "List names explicitly: `workflows: ['lint', 'build-runtime']`.\n"
        "## WARNING\n"
        "- `.github/workflows/dogfood.yml:35` — no concurrency.\n"
        "SUMMARY: 1 BLOCKING, 5 WARNING, 2 NIT\n"
    )
    out = subprocess.run([sys.executable, str(SCRIPT)], input=body,
                         capture_output=True, text=True, check=False)
    assert out.returncode == 0
    assert json.loads(out.stdout) == {
        "blocking": 1,
        "block": "- `.github/workflows/dogfood.yml:23` — check the workflow filter.\n"
                 "List names explicitly: `workflows: ['lint', 'build-runtime']`.",
    }


def _run(body: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)], input=body, text=True, capture_output=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_paragraph_opening_with_warning_does_not_end_the_block() -> None:
    # A prose sentence with WARNING should remain inside the BLOCKING block.
    body = (
        "**BLOCKING**\n\n`a.py:44`\n\n"
        "WARNING (elevado a bloqueante pela política): fallback silente. Fix: tornar obrigatório.\n\n"
        "**WARNING** (sem bloquear)\n\n`b.py:1`\n\n---\n\nSUMMARY: 1 BLOCKING, 1 WARNING, 0 NIT\n"
    )
    block = _run(body)["block"]
    assert "fallback silente" in block and "b.py:1" not in block


def test_marked_heading_followed_by_text_ends_the_block() -> None:
    # `**WARNING**: …` ends the block; `**BLOCKING: 1**` starts it.
    body = "**BLOCKING: 1**\n- a.py:1 quebra\n**WARNING**: b.py:2 depois\n\nSUMMARY: 1 BLOCKING, 1 WARNING, 0 NIT\n"
    assert _run(body)["block"] == "- a.py:1 quebra"


def test_bold_sentence_opening_with_blocking_is_not_a_heading() -> None:
    # A bold sentence beginning with BLOCKING is not a section heading.
    body = "**BLOCKING anteriores — corrigidos no HEAD:**\n- ok\n\nBLOCKING\n  L1: real\n\nSUMMARY: 1 BLOCKING, 0 WARNING, 0 NIT\n"
    assert _run(body)["block"] == "  L1: real"


def test_fenced_snippet_inside_the_block_is_kept() -> None:
    body = (
        "### BLOCKING\n\n- a.py:1 troque por:\n```py\nx = 1\n```\n- c.py:3 idem\n\n"
        "### WARNING\n\n- b.py:2\n\nSUMMARY: 2 BLOCKING, 1 WARNING, 0 NIT\n"
    )
    block = _run(body)["block"]
    assert "x = 1" in block and "c.py:3" in block and "b.py:2" not in block


def test_markup_around_the_summary_line_keeps_the_count() -> None:
    # Markdown variants observed in review summaries.
    for line in (
        "**SUMMARY: 2 BLOCKING, 1 WARNING, 0 NIT**",
        "**SUMMARY**: 2 BLOCKING, 1 WARNING, 0 NIT",
        "**SUMMARY:** 2 BLOCKING, 1 WARNING, 0 NIT",
        "## SUMMARY: 2 BLOCKING, 1 WARNING, 0 NIT",
        "`SUMMARY: 2 BLOCKING, 1 WARNING, 0 NIT`",
    ):
        assert _run(f"BLOCKING\n  L1: x\n\n---\n{line}\n")["blocking"] == 2, line


def test_marked_summary_line_ends_the_block() -> None:
    # Stop the BLOCKING block at a marked SUMMARY heading too.
    for closing in ("**SUMMARY:** 1 BLOCKING, 0 WARNING, 0 NIT", "### SUMMARY"):
        body = f"BLOCKING\n  L1: real\n\n{closing}\nRECOMMEND: corrigir\n\nSUMMARY: 1 BLOCKING, 0 WARNING, 0 NIT\n"
        assert _run(body)["block"] == "  L1: real", closing


def test_per_axis_or_split_summary_is_not_a_count() -> None:
    # Resumo por eixo (passo 5 da skill) e contagem abaixo de `## SUMMARY` não são
    # a linha do contrato: contar daria número de um eixo só, ou de outra linha.
    for body in (
        "SUMMARY: Standards 1 BLOCKING, 0 WARNING; Spec 1 BLOCKING\n",
        "## SUMMARY\n\n2 BLOCKING, 0 WARNING, 0 NIT\n",
    ):
        assert _run(body)["blocking"] == 0, body


def test_translated_closing_counts_like_the_english_one() -> None:
    # The same summary shape can arrive with Portuguese labels.
    for line in (
        "RESUMO: 0 BLOQUEIOS, 3 AVISOS, 2 PEQUENOS",
        "SUMÁRIO: 0 BLOQUEIOS, 1 AVISO, 2 PEQUENAS OBSERVAÇÕES",
        "SUMÁRIO: 0 BLOQUEIO, 0 AVISO, 3 PEQUENAS OBSERVAÇÕES",
    ):
        assert _run(f"BLOQUEIO\n\nAVISO\n  a.py:1 x\n\n{line}\n")["blocking"] == 0, line


def test_translated_blocking_section_reaches_the_issue_body() -> None:
    # A translated AVISO heading ends the copied BLOQUEIO section.
    body = (
        "BLOQUEIO\n  a.py:44: fallback silente. Correção: tornar obrigatório.\n\n"
        "AVISO\n  b.py:2: eval sobre config.\n\n"
        "PEQUENO\n  c.py:3: vírgula final.\n\n"
        "RESUMO: 1 BLOQUEIO, 1 AVISO, 1 PEQUENO\n"
    )
    out = _run(body)
    assert out["blocking"] == 1
    assert "fallback silente" in out["block"]
    assert "eval sobre config" not in out["block"], "o bloco termina no AVISO seguinte"


def test_prose_opening_with_translated_summary_word_does_not_end_the_block() -> None:
    # A sentence starting with RESUMO remains inside the preceding block.
    body = (
        "## BLOQUEIO\n- a.py:1 x\nRESUMO do problema: y\n- b.py:2 z\n\n"
        "RESUMO: 2 BLOQUEIOS, 0 AVISOS, 0 PEQUENOS\n"
    )
    out = _run(body)
    assert out["blocking"] == 2
    assert out["block"] == "- a.py:1 x\nRESUMO do problema: y\n- b.py:2 z"


def test_unobserved_translated_alias_does_not_end_the_block() -> None:
    body = (
        "BLOQUEIO\n  a.py:44: fallback silente.\n\n"
        "MENORE\n  ainda faz parte do bloqueio.\n\n"
        "AVISO\n  b.py:2: aviso real.\n\n"
        "RESUMO: 1 BLOQUEIO, 1 AVISO, 0 PEQUENO\n"
    )
    block = _run(body)["block"]
    assert "ainda faz parte do bloqueio" in block
    assert "aviso real" not in block


def test_translated_per_axis_summary_is_still_not_a_count() -> None:
    # A tolerância é de língua, não de forma: resumo por eixo continua fora.
    assert _run("RESUMO: Standards 1 BLOQUEIO; Spec 1 BLOQUEIO\n")["blocking"] == 0


def test_without_summary_line_never_raises_and_reports_zero() -> None:
    out = _run("Review sem formato.\n\nBLOCKING\n  algo\n")
    assert out == {"blocking": 0, "block": ""}


def test_comments_null_never_raises_and_reports_zero() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--comments"],
        input="null", text=True, capture_output=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"blocking": 0, "block": "", "url": "", "summary": "missing"}
