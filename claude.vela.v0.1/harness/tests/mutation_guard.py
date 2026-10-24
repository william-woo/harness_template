#!/usr/bin/env python3
"""게이트 검사기의 **판정 지점**을 도출해 하나씩 무력화하고, 테스트가 죽는지 본다.

## 왜 이것이 있나

F021 에서 **세 라운드 연속**, 같은 결함이 그 지적을 고친 바로 그 커밋에서 재발했다:

| 라운드 | 지적 | 그때 통과한 것 |
|---|---|---|
| 3차 MUST-1 | 두 수정에 회귀 테스트 0건 | 37 테스트 + `lint --strict` |
| 5차 MUST-2 | 새 동작 2건 테스트 0건 | 그리고 "집합을 순회하므로 자동으로 따라온다" 는 **거짓 주장** |
| 6차 MUST-3 | 새 동작 4건 테스트 0건 | — |

세 번 다 처방은 "다음부터 테스트를 쓰자" 였고 세 번 다 샜다. 사람의 자기 평가에
의존했기 때문이다. **테스트의 존재와 통과**는 묻기 쉽지만, 물어야 하는 것은
**그 동작이 관측되는가** 다. 둘은 다른 질문이고, 전자만 물으면 세 라운드 내내
"충족" 으로 읽힌다 (리뷰어 판정: "재검토가 다룰 것은 코드가 아니라 그 작업 규율이다").

## 무엇을 **도출**하는가 (손 목록 0)

아홉 번째 공회전 형태가 "표는 데이터가 됐는데 표를 지키는 쪽은 다시 손 목록" 이었다.
그래서 대상을 적지 않고 **코드에서 뽑는다**:

    _GATE_CHECKERS → _CHECKERS 등록부의 함수 → 모듈 내 호출 폐포
                   → 그 안의 `_issue(…, BLOCK|CONCERN, …)` 호출

검사기·규칙 행·커맨드가 하나 늘면 지점이 **자동으로** 는다.
`_GATE_CHECKERS` 를 몰래 줄여 회피하는 길은 `GateFailureTest` 가 이미 막는다
(5차 M7b 로 신설) — 두 가드가 맞물린다.

## 연산자는 **크래시를 내지 않는다**

라벨 식별자 `BLOCK|CONCERN` → `INFO` **만** 치환한다. 같은 네임스페이스의 상수라
문법·런타임 모두 안전하고, BLOCK 을 *없애기만* 하므로 실패할 수 있는 테스트는
"BLOCK 이 있어야 한다" 고 주장하는 테스트뿐이다 — **거짓 kill 이 구조적으로 0** 이다.

메시지까지 치환하는 판을 재 봤더니 67 중 20 이 문법 파괴, 그 중 11건이 거짓 kill
이었다. 크래시는 예외 → BLOCK 강등으로 "죽었다" 처럼 보이기 때문에, 연산자가
안전하지 않으면 하네스 전체가 거짓이 된다.

## 모든 사본에 **동시에** 건다

메인만 바꾸면 `LINT-CO` 의 실트리 테스트가 "lint.py 가 갈렸다" 로 실패해
**전 변이가 거짓 kill** 이 된다 (실측 67 중 54). 2026-10-22 에 같은 함정을 밟았다.

## 이 하네스 자신이 공회전이 되지 않도록

**의미-중립 대조**를 먼저 돌린다 — 바이트는 바꾸되 의미는 같은 변이(`BLOCK`→`(BLOCK)`).
그것이 죽으면 기준선이 빨간 것이므로 **보고를 거부**하고 exit 2 한다. 사본 하나만
변이하는 사고(mH1)가 정확히 이 대조에 걸린다.

생존 명단을 리포 안에 **저장하지 않는다**. 저장하는 순간 "감시 대상의 자기 신고"
(열 번째 공회전 형태)가 되살아난다 — 범위는 매번 git 에서 다시 계산한다.

## 쓰는 법

    python3 tests/mutation_guard.py                 # 변경-귀속 (기본, HEAD~1)
    python3 tests/mutation_guard.py --base <ref>    # 리뷰 base 와 같은 ref 를 쓴다
    python3 tests/mutation_guard.py --all           # 전수 (느리다)

`--base` 범위에서 생존이 1건이라도 있으면 exit 1 이다. 그것이 "이번 변경이 만든
동작 중 아무 테스트도 요구하지 않는 것" 이다.

## 덮지 못하는 것 (검사기를 더 똑똑하게 만들어 덮지 않는다)

- 판정도 커맨드도 아닌 동작 (예: 캐시 파일에 필드 하나 추가)
- 메시지 **문구**의 정확성 — 라벨만 보므로 문구가 틀려도 통과한다
- `CONCERN` 지점은 `--strict` 가 세지 않아 변이가 약하다 (메시지만 단언하는
  테스트는 안 죽는다)
- 권한 기반 테스트가 skip 되는 환경(root)에서는 그 지점이 생존으로 보고된다

이 넷은 규율과 리뷰의 몫으로 남긴다. 경계를 적어 두는 것이 경계를 넓히는 것보다 낫다.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_LINT_REL = ".claude/bin/lint.py"

#: 변이를 죽일 수 있는 스위트. 여기 없는 모듈은 kill set 에 없으므로 생존이 과대 보고된다.
_TESTS = ["tests.test_lint_overlay", "tests.test_lint_ssot", "tests.test_backup_excludes",
          "tests.test_host_render", "tests.test_pre_bash_repo_scope", "tests.test_verify_loop"]


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("_lint_under_mutation", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _functions(tree) -> dict:
    return {n.name: n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _callees(fn) -> set:
    out = set()
    for c in ast.walk(fn):
        if isinstance(c, ast.Call):
            f = c.func
            nm = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
            if nm:
                out.add(nm)
    return out


def _forward_closure(funcs: dict, entries: set) -> set:
    """`entries` 에서 (간접) 호출되는 함수 전부 — 게이트 검사기가 닿는 범위."""
    seen, stack = set(), list(entries)
    while stack:
        name = stack.pop()
        if name in seen or name not in funcs:
            continue
        seen.add(name)
        stack.extend(_callees(funcs[name]) & set(funcs) - seen)
    return seen


def _reverse_closure(funcs: dict, touched: set) -> set:
    """`touched` 를 (간접) 호출하는 함수 전부 — 이번 변경의 영향 범위."""
    calls = {n: _callees(f) & set(funcs) for n, f in funcs.items()}
    affected, stack = set(touched), list(touched)
    while stack:
        cur = stack.pop()
        for name, callees in calls.items():
            if cur in callees and name not in affected:
                affected.add(name)
                stack.append(name)
    return affected


def _owner_of_line(tree) -> dict:
    """줄 번호 → 그 줄을 품은 **가장 안쪽** 함수 이름."""
    owner: dict = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for ln in range(n.lineno, (n.end_lineno or n.lineno) + 1):
                prev = owner.get(ln)
                if prev is None or prev[0] < n.lineno:
                    owner[ln] = (n.lineno, n.name)
    return {ln: v[1] for ln, v in owner.items()}


def judgement_sites(src: str, allowed: set) -> list:
    """`allowed` 안의 함수가 내는 BLOCK·CONCERN 판정 지점."""
    tree = ast.parse(src)
    owner = _owner_of_line(tree)
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        nm = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
        if nm != "_issue" or len(n.args) < 2:
            continue
        lab = n.args[1]
        if not (isinstance(lab, ast.Name) and lab.id in ("BLOCK", "CONCERN")):
            continue
        fn = owner.get(n.lineno, "?")
        if fn not in allowed:
            continue
        out.append({"fn": fn, "label": lab.id, "line": lab.lineno,
                    "col": lab.col_offset, "end_col": lab.end_col_offset})
    return sorted(out, key=lambda s: (s["line"], s["col"]))


def apply_mutation(src: str, site: dict) -> str:
    lines = src.splitlines(keepends=True)
    i = site["line"] - 1
    ln = lines[i]
    found = ln[site["col"]:site["end_col"]]
    if found != site["label"]:
        raise AssertionError(f"오프셋이 어긋났다: {found!r} != {site['label']!r}")
    mutated = "".join(lines[:i] + [ln[:site["col"]] + site.get("to", "INFO")
                                   + ln[site["end_col"]:]] + lines[i + 1:])
    ast.parse(mutated)      # 치환이 문법을 깨면 거짓 kill 이 된다 — 미리 거른다
    return mutated


def _run_one(task) -> dict:
    idx, site, src, repo, work_root, only_main = task
    work = Path(work_root) / f"m{idx:03d}"
    if not work.exists():
        subprocess.run(["cp", "-al", str(repo), str(work)], check=True, capture_output=True)
    mutated = apply_mutation(src, site)
    targets = [work / _LINT_REL]
    if not only_main:
        targets += sorted(work.glob("src/harness_template/*/harness/" + _LINT_REL))
    for t in targets:
        t.unlink()          # 하드링크를 끊는다 — 원본을 건드리지 않기 위해
        t.write_text(mutated, encoding="utf-8")
    t0 = time.time()
    res = subprocess.run([sys.executable, "-m", "unittest", "-f", *_TESTS],
                         cwd=str(work), capture_output=True, text=True, timeout=900)
    killer = next((l.strip() for l in res.stderr.splitlines()
                   if l.startswith(("FAIL: ", "ERROR: "))), "")
    return {**site, "killed": res.returncode != 0, "killer": killer,
            "sec": round(time.time() - t0, 1)}


def changed_functions(repo: Path, base: str, funcs: dict) -> set:
    """`base..HEAD` 가 건드린 줄을 품은 함수."""
    diff = subprocess.run(["git", "diff", "-U0", f"{base}..HEAD", "--", _LINT_REL],
                          cwd=str(repo), capture_output=True, text=True).stdout
    changed: set = set()
    for line in diff.splitlines():
        if not line.startswith("@@"):
            continue
        part = line.split("+")[1].split("@@")[0].strip()
        start, _, cnt = part.partition(",")
        start, cnt = int(start), int(cnt or 1)
        changed |= set(range(start, start + max(cnt, 1)))
    return {n for n, f in funcs.items()
            if any(f.lineno <= l <= (f.end_lineno or f.lineno) for l in changed)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", default="HEAD~1",
                    help="변경 귀속의 기준 ref — **리뷰 base 와 같은 것**을 쓴다")
    ap.add_argument("--all", action="store_true", help="전수 (변경 귀속 없이)")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("W", "8")))
    ap.add_argument("--work", default=None, help="작업 디렉토리 (기본: 임시)")
    args = ap.parse_args()

    repo = _ROOT
    src = (repo / _LINT_REL).read_text(encoding="utf-8")
    tree = ast.parse(src)
    funcs = _functions(tree)
    mod = _load(repo / _LINT_REL)
    entries = {mod._CHECKERS[c][1].__name__ for c in mod._GATE_CHECKERS if c in mod._CHECKERS}
    allowed = _forward_closure(funcs, entries)
    all_sites = judgement_sites(src, allowed)

    if args.all:
        targets = all_sites
        scope_note = "전수"
    else:
        touched = changed_functions(repo, args.base, funcs)
        affected = _reverse_closure(funcs, touched)
        targets = [s for s in all_sites if s["fn"] in affected]
        scope_note = (f"변경 귀속 base={args.base} · 건드린 함수 {len(touched)} "
                      f"→ 영향 {len(affected)}")
        if touched:
            print(f"  건드린 함수: {', '.join(sorted(touched))}")

    print(f"게이트 진입점 {len(entries)} → 호출 폐포 {len(allowed)} 함수 "
          f"→ 판정 지점 {len(all_sites)}")
    print(f"범위: {scope_note} → 대상 {len(targets)}")
    if not targets:
        # **PASS 라고 말하지 않는다.** 범위가 0 인 것과 전부 관측되는 것은 다르다.
        print("대상 0 — 이 변경은 게이트 검사기의 판정에 닿지 않는다")
        return 0

    import tempfile
    with tempfile.TemporaryDirectory(dir=args.work) as tmp:
        # 의미-중립 대조를 **먼저**. 이것이 죽으면 기준선이 빨간 것이고 아래가 전부 거짓이다.
        ctrl_site = {**targets[0], "to": "(" + targets[0]["label"] + ")"}
        ctrl = _run_one((999, ctrl_site, src, repo, tmp, False))
        print(f"대조(의미-중립): killed={ctrl['killed']} {ctrl['killer'][:90]}")
        if ctrl["killed"]:
            print("!! 기준선이 빨갛다 — 결과를 보고하지 않는다")
            return 2

        t0 = time.time()
        tasks = [(i, s, src, repo, tmp, False) for i, s in enumerate(targets)]
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            results = list(ex.map(_run_one, tasks))
        elapsed = time.time() - t0

    survivors = [r for r in results if not r["killed"]]
    print(f"\n{len(results)} 변이 · 생존 {len(survivors)} · {elapsed:.0f}s "
          f"(워커 {args.workers})")
    if survivors:
        print("\n생존 — 어떤 테스트도 이 판정을 요구하지 않는다:")
        for r in survivors:
            print(f"  L{r['line']:5d}  {r['label']:8s} {r['fn']}")
        print("\n이 지점들이 BLOCK/CONCERN 을 내야 하는 상황을 단언하는 테스트를 쓰라.")
        return 1
    print("생존 0 — 범위 안의 모든 판정이 테스트에 관측된다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
