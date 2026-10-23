#!/usr/bin/env python3
"""
judge_variance — 판정 분산을 직접 측정한다 (산문형 rubric vs 항목형 rubric).

스위트 통과율로 판정 품질을 재려면 사이클 전체의 분산에 묻힌다 (측정 10: 6 사이클/구간으로는
효과 크기가 안 나온다). 판정이 개선됐는지는 **판정 자체**를 재야 한다 — 같은 산출물에 N회
판정해 verdict 가 얼마나 흔들리는지, 그리고 심어둔 결함을 잡는지.

Rubrics-as-Rewards 의 청구가 정확히 이것이다: 구조화된 채점표가 **분산을 줄인다**.

공정성 조건: 두 구간에 **같은 내용**을 주고 **구조만** 다르게 한다. 둘 다 도구를 쓰지 않고
프롬프트에 담긴 내용만으로 판정한다.

사용:
    python3 tests/judge_variance.py --repeats 6
    python3 tests/judge_variance.py --repeats 6 --case no_docstring
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / ".claude" / "bin"))

# 결함을 심은 고정 대상 — ground truth 를 우리가 안다.
CASES = {
    "no_docstring": {
        "truth": "revision",
        "truth_item": ("M1", "unmet"),   # docstring 누락
        "why": "word_count 에 docstring 이 없다 (테스트는 통과)",
        "content": '''--- word_count.py ---
def word_count(text):
    parts = text.split()
    return len(parts)

--- test_word_count.py ---
import word_count

def test_basic():
    assert word_count.word_count("a b c") == 3

test_basic()
print("PASS")
''',
    },
    "clean": {
        "truth": "pass",
        "truth_item": ("M1", "met"),
        "why": "docstring·테스트·assert 모두 갖춘 정상 산출물",
        "content": '''--- word_count.py ---
def word_count(text):
    """공백으로 구분된 단어 개수를 센다."""
    parts = text.split()
    return len(parts)

--- test_word_count.py ---
import word_count

def test_basic():
    """기본 3단어 입력에서 3을 반환한다."""
    assert word_count.word_count("a b c") == 3

test_basic()
print("PASS")
''',
    },
}

_PROSE_RUBRIC = """MUST (미해결 시 revision):
- docstring/JSDoc — 함수·클래스에 존재
- 단위 테스트 — 새 기능/변경에 포함, 통과
- 에러 처리 — 외부 I/O·API·사용자 입력 경계에서 방어
- 보안 — 자격증명 하드코딩 없음, 입력 검증
- Surgical Changes — 무관한 대량 변경 없음
- 계약 준수 — 외부 의존성 정책 위반 없음"""


def _prose_prompt(content: str) -> str:
    """산문형 구간: 기존 rubric 을 주고 단일 verdict 를 요구한다."""
    return (
        "You are reviewing code against a rubric.\n"
        "Judge from the content below only. Do NOT use any tool.\n\n"
        f"===== 판정 대상 내용 =====\n{content}===== 내용 끝 =====\n\n"
        f"RUBRIC — code-review\n{_PROSE_RUBRIC}\n\n"
        "MUST 가 하나라도 미해결이면 revision, 전부 해결이면 pass 다.\n"
        "마지막 줄에 정확히 이 형식으로만 답하라:\n"
        "VERDICT: <pass|revision>\n"
    )


def _run(prompt: str, model: str) -> str:
    import cycle_driver as cd
    _rc, out = cd._opencode_run(None, prompt, model=model)
    return out


def _prose_verdict(out: str) -> str:
    """산문형 응답에서 verdict 를 추출한다 (형식 위반은 'unparseable')."""
    for line in reversed(out.splitlines()):
        s = line.strip().upper()
        if s.startswith("VERDICT:"):
            v = s.split(":", 1)[1].strip().lower()
            if v in ("pass", "revision"):
                return v
    return "unparseable"


def main() -> None:
    ap = argparse.ArgumentParser(description="판정 분산 측정 (산문형 vs 항목형)")
    ap.add_argument("--repeats", type=int, default=6)
    ap.add_argument("--case", default="no_docstring", choices=sorted(CASES))
    ap.add_argument("--role", default="reviewer")
    args = ap.parse_args()

    import aif_judge as aj
    import cycle_driver as cd

    case = CASES[args.case]
    model = cd._role_models().get(args.role)
    items = aj.parse_items("code-review")
    iid, want = case["truth_item"]
    print(f"=== case={args.case} · ground truth={case['truth']} ({case['why']}) ===")
    print(f"    모델={model} · 반복={args.repeats}\n")

    prose = Counter()
    for i in range(1, args.repeats + 1):
        v = _prose_verdict(_run(_prose_prompt(case["content"]), model))
        prose[v] += 1
        print(f"  [산문형] {i}/{args.repeats} → {v}")

    item_overall = Counter()
    item_target = Counter()
    invalid = 0
    for i in range(1, args.repeats + 1):
        out = _run(aj.build_prompt("code-review", items, args.case, case["content"]), model)
        res = aj.validate(items, out)
        if not res["valid"]:
            invalid += 1
            print(f"  [항목형] {i}/{args.repeats} → 무효 ({res['reason'][:50]})")
            continue
        agg = aj.aggregate(items, [res])
        item_overall[agg["overall"]] += 1
        item_target[agg["items"][iid]["decided"]] += 1
        print(f"  [항목형] {i}/{args.repeats} → {agg['overall']} ({iid}={agg['items'][iid]['decided']})")

    def rate(c: Counter, key: str, n: int) -> str:
        return f"{c[key]}/{n} ({100 * c[key] // n if n else 0}%)"

    n = args.repeats
    valid_n = n - invalid
    print(f"\n=== 결과 (ground truth: 전체={case['truth']}, {iid}={want}) ===")
    print(f"  산문형 정답률   : {rate(prose, case['truth'], n)}   분포 {dict(prose)}")
    print(f"  항목형 정답률   : {rate(item_overall, case['truth'], valid_n)}   분포 {dict(item_overall)}"
          f"  (무효 {invalid})")
    print(f"  항목형 {iid} 정답률: {rate(item_target, want, valid_n)}   분포 {dict(item_target)}")
    print("\n  분산이 낮고 정답률이 높은 쪽이 게이트로 쓸 만하다.")
    print("  주의: 표본이 작으면 두 구간 차이는 노이즈다 — 반복을 늘려 재현을 확인한다.")

    out_path = _ROOT / ".claude" / "state" / "aif" / f"variance-{args.case}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "case": args.case, "truth": case["truth"], "repeats": n, "model": model,
        "prose": dict(prose), "items_overall": dict(item_overall),
        "items_target": {"item": iid, "want": want, "tally": dict(item_target)},
        "invalid_judgments": invalid,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n기록: {out_path.relative_to(_ROOT)}")


if __name__ == "__main__":
    main()
