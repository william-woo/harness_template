#!/usr/bin/env python3
"""
autoresearch — 무인 스위트를 적합도 함수로 쓰는 **하네스 자가 실험 루프** (ADR-019).

karpathy/autoresearch 의 구조를 하네스에 이식한다. 원본은 고정된 `prepare.py` 를 두고 에이전트가
`train.py` **한 파일만** 고쳐 5분 고정 예산으로 학습을 돌린 뒤 단일 스칼라(val_bpb)로 keep/discard
한다. 사람은 코드를 직접 고치지 않고 `program.md`(지침)를 손보고 로그를 검토한다.

| autoresearch | 이 스크립트 |
|---|---|
| `prepare.py` (고정) | 게이트·oracle·시나리오 = **불변** (해시 매니페스트로 강제) |
| `train.py` (유일한 변경 대상) | `policy/<role>.md` — 역할 지시 오버레이 |
| `program.md` (사람이 쓰는 지침) | `.claude/state/autoresearch/program.md` |
| val_bpb (단일 스칼라) | 스위트 PASS 율 (거짓 결과 1건이면 즉시 실격) |
| 5분 고정 예산 | 시나리오 집합 × 반복 수 (실험마다 동일) |
| keep / discard | 자동 — 단 **원장(ledger)에만** 반영 |
| 사람이 로그 검토 + program.md 수정 | 사람이 `promote` 로 하네스 본체 반영 |

**핵심 계약 — 자동 채택은 "실험 결과"까지**: 이 스크립트는 하네스 본체를 절대 수정하지 않는다.
승자 정책은 `.claude/state/autoresearch/` 안에 머물고, `.claude/policy/`(하네스 본체)로 옮기는
것은 `promote` 서브커맨드 + 명시적 `--yes` 로만 가능하다. autoresearch 의 "결과는 shipped
improvement 가 아니라 starting hypothesis" 를 코드로 강제한 것이다.

**reward hacking 방지 (구조적)**:
  ① 변경 표면은 `policy/<role>.md` 뿐 — 게이트·oracle·시나리오 파일 해시가 실험 전후로 바뀌면 무효.
  ② 후보 구간에서 ACCURACY(거짓 결과) 판정이 1건이라도 나오면 점수와 무관하게 **실격**.
     "판정을 무르게 만들어 점수를 올리는" 방향이 이득이 되지 않게 한다.
  ③ 베이스라인을 **같은 배치에서 다시 측정**(paired)한다 — 낡은 기준선 대비 노이즈를 이득으로
     오인하지 않기 위해서다.

사용:
    python3 .claude/bin/autoresearch.py init
    python3 .claude/bin/autoresearch.py run --experiments 3 --scenarios S01,S05 --repeats 1
    python3 .claude/bin/autoresearch.py status
    python3 .claude/bin/autoresearch.py promote exp-003 --yes
    python3 .claude/bin/autoresearch.py self
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

_BIN = Path(__file__).resolve().parent
_ROOT = _BIN.parent.parent
# 실험 공간. 결과·샌드박스가 수 GB 로 늘 수 있어 `AUTORESEARCH_DIR` 로 리포 밖에 둘 수 있다.
_AR = Path(os.environ["AUTORESEARCH_DIR"]) if os.environ.get("AUTORESEARCH_DIR") \
    else _ROOT / ".claude" / "state" / "autoresearch"
_PROGRAM = _AR / "program.md"
_BEST = _AR / "best"                      # 현재 챔피언 정책 (실험 공간 — 하네스 본체 아님)
_LEDGER = _AR / "ledger.jsonl"
_PROMOTED = _ROOT / ".claude" / "policy"  # 하네스 본체 — promote 로만 기록된다

# 실험이 손대면 안 되는 파일 (autoresearch 의 prepare.py 상당)
_IMMUTABLE = [
    ".claude/bin/cycle_driver.py",
    ".claude/bin/autoresearch.py",
    "tests/suite/run_suite.py",
]
_ROLES = ("developer", "reviewer", "qa", "architect", "planner", "researcher")

_PROGRAM_TEMPLATE = """# autoresearch program — 로컬 LLM 하네스 개선 지침

> 이 파일은 **사람이 쓰는 지침서**다. autoresearch 는 이 지침을 읽고 정책 후보를 제안한다.
> 코드를 직접 고치는 대신 이 파일을 고쳐서 실험 방향을 조종한다 (karpathy/autoresearch 와 동일).

## 목표
로컬 LLM(qwen2.5:32b)이 하네스 사이클(개발→채점→리뷰→QA)을 **더 자주 완주**하게 만든다.
측정값은 무인 스위트의 PASS 율이다.

## 변경할 수 있는 것
`policy/<role>.md` — 역할 에이전트에게 과제 앞에 붙는 지시문뿐이다.
역할: developer / reviewer / qa / architect / planner / researcher

## 변경할 수 없는 것 (실험 무효 처리됨)
게이트·oracle·시나리오·드라이버 코드. 판정 기준을 무르게 만드는 방향은 실격이다.

## 관찰된 약점 (여기에 사람이 계속 추가한다)
- 다중 파일 + import 체인 과제의 재현율이 낮다 (모듈을 안 만들고 테스트에 함수를 직접 정의).
- 리팩토링 과제에서 요구된 심볼·구조 토큰을 누락한다.
- 산출물에 이스케이프된 개행/따옴표, 탭 들여쓰기가 섞인다.

## 지시문 작성 규칙
- 짧고 명령형으로. 5줄 이내. (긴 지시는 14B~32B 에서 도구 호출을 방해한다 — 측정 08 라운드 6)
- 과제 내용이 아니라 **작업 방식**을 지시한다.
- 테스트를 약화시키거나 검증을 우회하라는 지시는 금지.
"""


def _rel(p: Path) -> str:
    """리포 기준 상대 경로로 표시한다 (실험 공간이 리포 밖이면 절대 경로 그대로)."""
    try:
        return str(p.relative_to(_ROOT))
    except ValueError:
        return str(p)


def _log(msg: str) -> None:
    print(msg, flush=True)


def _manifest() -> dict[str, str]:
    """불변 파일들의 SHA-256 요약을 반환한다."""
    out = {}
    for rel in _IMMUTABLE:
        p = _ROOT / rel
        if p.is_file():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return out


def _policy_files(d: Path) -> list[Path]:
    return sorted(p for p in d.glob("*.md")) if d.is_dir() else []


def _policy_snapshot(d: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in _policy_files(d)}


def _read_ledger() -> list[dict]:
    if not _LEDGER.is_file():
        return []
    out = []
    for line in _LEDGER.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def _append_ledger(rec: dict) -> None:
    _AR.mkdir(parents=True, exist_ok=True)
    with _LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ─────────────────────────────── 적합도 함수 ────────────────────────────────

def _suite_arm(exp_dir: Path, arm: str, policy_dir: Path,
               scenarios: list[str], repeats: int, timeout: int) -> dict:
    """
    한 구간(arm)의 스위트를 실행해 점수를 반환한다.

    Args:
        exp_dir: 실험 디렉토리 (결과·샌드박스가 여기 격리된다)
        arm: "base" 또는 "cand"
        policy_dir: 이 구간에서 주입할 정책 디렉토리 (절대 경로)
        scenarios: 시나리오 ID 목록 (예: ["S01", "S05"])
        repeats: 반복 횟수 — LLM 확률성 때문에 1회 결과는 노이즈다
        timeout: 구간 전체 제한 시간(초)

    Returns:
        {"pass": n, "total": n, "accuracy": n, "records": [...]}
    """
    res = exp_dir / f"results-{arm}"
    sb = exp_dir / f"sandboxes-{arm}"
    res.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["HARNESS_POLICY_DIR"] = str(policy_dir)
    env["SUITE_RESULTS"] = str(res)
    env["SUITE_SANDBOX"] = str(sb)
    env["SUITE_TEMPLATE"] = str(_ROOT)

    for r in range(1, repeats + 1):
        if sb.is_dir():
            shutil.rmtree(sb, ignore_errors=True)
        cmd = [sys.executable, "tests/suite/run_suite.py", "--round", str(r), *scenarios]
        _log(f"    [{arm}] 반복 {r}/{repeats} — {' '.join(scenarios)}")
        try:
            subprocess.run(cmd, cwd=_ROOT, env=env, timeout=timeout,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            _log(f"    [{arm}] 반복 {r} 제한시간 초과 — 부분 결과로 채점")

    records = []
    for f in sorted(res.glob("round*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except ValueError:
                    pass
    return {
        "pass": sum(1 for r in records if r.get("verdict") == "PASS"),
        "total": len(records),
        "accuracy": sum(1 for r in records if r.get("verdict") == "ACCURACY"),
        "records": records,
    }


def _evidence(records: list[dict], limit: int = 3) -> str:
    """실패한 실행에서 제안 근거로 쓸 증거를 뽑는다 (모델에 넘길 컴팩트 요약)."""
    out = []
    for r in records:
        if r.get("verdict") == "PASS":
            continue
        notes = "; ".join((j.get("notes") or "")[:120] for j in r.get("judges", [])[-2:])
        tail = (r.get("driver_tail") or "")[-350:].replace("\n", " ")
        out.append(f"- {r['id']} {r['name']} → {r['verdict']}\n  판정: {notes}\n  로그: {tail}")
        if len(out) >= limit:
            break
    return "\n".join(out) or "- (실패 사례 없음)"


# ─────────────────────────────── 후보 제안 ────────────────────────────────

def _propose(program: str, current: dict[str, str], evidence: str) -> tuple[str, str] | None:
    """
    로컬 LLM 에게 다음 정책 후보를 제안하게 한다.

    cycle_driver 의 호스트 호출 계층(머신 락 · 지수 백오프 · PWD 보정)을 그대로 재사용한다 —
    측정 08 에서 굳어진 부분이라 다시 구현하면 같은 결함을 되풀이하게 된다.

    Returns:
        (role, directives) — 파싱 실패 시 None (추측하지 않고 실험을 무효 처리한다).
    """
    sys.path.insert(0, str(_BIN))
    import cycle_driver as cd  # noqa: E402  (경로 주입 후에만 import 가능)

    cur = "\n".join(f"### {n}\n{t.strip()[:600]}" for n, t in current.items()) or "(없음 — 첫 실험)"
    prompt = (
        "You improve the instructions given to coding agents. Output ONLY the block below.\n\n"
        f"PROGRAM (human-written goals and constraints):\n{program[:1800]}\n\n"
        f"CURRENT POLICY:\n{cur}\n\n"
        f"RECENT FAILURES (evidence):\n{evidence[:1500]}\n\n"
        "Propose ONE improved policy for ONE role. Address a specific failure above.\n"
        "Rules: at most 5 imperative lines; about HOW to work, not about the task; "
        "never weaken tests or skip verification.\n\n"
        "Answer in exactly this format:\n"
        f"ROLE: <one of {', '.join(_ROLES)}>\n"
        "POLICY:\n<line>\n<line>\n"
    )
    rc, out = cd._opencode_run(None, prompt, model=cd._role_models().get("researcher"))
    if rc != 0 and not out.strip():
        return None

    m = re.search(r"ROLE:\s*([a-z-]+)", out)
    p = re.search(r"POLICY:\s*\n(.+)", out, re.S)
    if not m or not p or m.group(1) not in _ROLES:
        return None
    text = p.group(1).strip()
    text = re.sub(r"^```[a-z]*\n?|```$", "", text, flags=re.M).strip()
    lines = [ln for ln in text.splitlines() if ln.strip()][:5]
    if not lines:
        return None
    return m.group(1), "\n".join(lines)[:1200]


# ─────────────────────────────── 서브커맨드 ────────────────────────────────

def cmd_init(args) -> int:
    """program.md 와 실험 공간을 scaffold 한다 (기존 파일은 보존)."""
    _AR.mkdir(parents=True, exist_ok=True)
    _BEST.mkdir(parents=True, exist_ok=True)
    if not _PROGRAM.is_file():
        _PROGRAM.write_text(_PROGRAM_TEMPLATE, encoding="utf-8")
        _log(f"✅ program.md 생성 → {_rel(_PROGRAM)}")
    else:
        _log(f"ⓘ program.md 이미 존재 (보존) → {_rel(_PROGRAM)}")
    for p in _policy_files(_PROMOTED):
        shutil.copy2(p, _BEST / p.name)
    _log(f"ⓘ 챔피언 정책 {len(_policy_files(_BEST))}개 (하네스 본체에서 승계)")
    _log("다음: python3 .claude/bin/autoresearch.py run --experiments 1 --scenarios S01 --repeats 1")
    return 0


def cmd_run(args) -> int:
    """실험 루프: 제안 → paired 실행 → 채점 → keep/discard → 원장 기록."""
    if not _PROGRAM.is_file():
        _log("❌ program.md 가 없다 — 먼저 `autoresearch.py init`")
        return 1
    _BEST.mkdir(parents=True, exist_ok=True)
    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    program = _PROGRAM.read_text(encoding="utf-8")
    started = time.time()
    n_done = len({r["exp"] for r in _read_ledger() if "exp" in r})

    for i in range(args.experiments):
        if args.budget_min and (time.time() - started) / 60 >= args.budget_min:
            _log(f"⏹ 예산 {args.budget_min}분 소진 — 중단")
            break
        exp = f"exp-{n_done + i + 1:03d}"
        exp_dir = _AR / exp
        exp_dir.mkdir(parents=True, exist_ok=True)
        _log(f"\n=== {exp} — 시나리오 {','.join(scenarios)} × {args.repeats}회 ===")

        before = _manifest()
        current = _policy_snapshot(_BEST)

        # 1. 베이스라인 측정 (같은 배치 — 낡은 기준선 대비 비교를 하지 않는다)
        _log("  ① 베이스라인 측정")
        base = _suite_arm(exp_dir, "base", _BEST, scenarios, args.repeats, args.timeout)

        # 2. 후보 제안
        _log("  ② 후보 제안 (로컬 LLM)")
        prop = _propose(program, current, _evidence(base["records"]))
        if not prop:
            _log("  ⚠️ 제안 파싱 실패 — 실험 무효 (추측하지 않는다)")
            _append_ledger({"exp": exp, "outcome": "INVALID", "reason": "proposal-unparseable",
                            "base": f"{base['pass']}/{base['total']}"})
            continue
        role, directives = prop
        cand_dir = exp_dir / "policy"
        cand_dir.mkdir(exist_ok=True)
        for name, text in current.items():
            (cand_dir / name).write_text(text, encoding="utf-8")
        (cand_dir / f"{role}.md").write_text(directives + "\n", encoding="utf-8")
        _log(f"  제안 대상: {role}\n{chr(10).join('    | ' + l for l in directives.splitlines())}")

        # 3. 후보 측정
        _log("  ③ 후보 측정")
        cand = _suite_arm(exp_dir, "cand", cand_dir, scenarios, args.repeats, args.timeout)

        # 4. 무결성 검사 — 게이트가 바뀌었으면 점수는 의미가 없다
        after = _manifest()
        if after != before:
            changed = [k for k in before if after.get(k) != before[k]]
            _log(f"  ❌ 불변 파일 변경 감지 {changed} — 실험 무효")
            _append_ledger({"exp": exp, "outcome": "INVALID", "reason": "immutable-changed",
                            "changed": changed})
            continue

        # 5. 판정
        b_rate = base["pass"] / base["total"] if base["total"] else 0.0
        c_rate = cand["pass"] / cand["total"] if cand["total"] else 0.0
        rec = {
            "exp": exp, "role": role, "scenarios": scenarios, "repeats": args.repeats,
            "base": f"{base['pass']}/{base['total']}", "cand": f"{cand['pass']}/{cand['total']}",
            "delta": round(c_rate - b_rate, 3), "cand_accuracy": cand["accuracy"],
            "policy": directives, "secs": round(time.time() - started),
        }
        if cand["accuracy"] > 0:
            rec["outcome"] = "DISQUALIFIED"
            rec["reason"] = "candidate produced false results"
            _log(f"  ⛔ 실격 — 후보 구간에서 거짓 결과 {cand['accuracy']}건")
        elif cand["total"] == 0 or base["total"] == 0:
            rec["outcome"] = "INVALID"
            rec["reason"] = "no records"
            _log("  ⚠️ 실행 기록 없음 — 무효")
        elif cand["pass"] > base["pass"]:
            rec["outcome"] = "KEEP"
            for p in _policy_files(_BEST):
                p.unlink()
            for p in _policy_files(cand_dir):
                shutil.copy2(p, _BEST / p.name)
            _log(f"  ✅ KEEP — {rec['base']} → {rec['cand']} (챔피언 갱신, 하네스 본체는 미변경)")
        else:
            rec["outcome"] = "DISCARD"
            _log(f"  ↩︎ DISCARD — {rec['base']} → {rec['cand']} (개선 없음)")
        _append_ledger(rec)

    _log("\n원장: " + _rel(_LEDGER))
    _log("승자를 하네스에 반영하려면 사람 승인이 필요하다: autoresearch.py promote <exp> --yes")
    return 0


def cmd_status(args) -> int:
    """원장 요약 + 현재 챔피언 정책을 표시한다."""
    led = _read_ledger()
    if not led:
        _log("실험 기록 없음 — `autoresearch.py run` 으로 시작")
        return 0
    _log(f"=== 실험 {len(led)}건 ===")
    for r in led:
        mark = {"KEEP": "✅", "DISCARD": "↩︎", "DISQUALIFIED": "⛔", "INVALID": "⚠️"}.get(r.get("outcome"), "?")
        _log(f"  {mark} {r.get('exp')} [{r.get('outcome')}] {r.get('role','-')} "
             f"{r.get('base','-')} → {r.get('cand','-')} {r.get('reason','')}")
    _log(f"\n=== 챔피언 정책 ({_rel(_BEST)}) — 실험 공간, 하네스 본체 아님 ===")
    for p in _policy_files(_BEST):
        _log(f"  ▸ {p.stem}\n" + "\n".join("      " + l for l in p.read_text(encoding='utf-8').strip().splitlines()))
    promoted = _policy_files(_PROMOTED)
    _log(f"\n=== 하네스 본체 정책 ({_rel(_PROMOTED)}) — 사람이 승인한 것만 ===")
    _log("  " + (", ".join(p.stem for p in promoted) if promoted else "(없음)"))
    return 0


def cmd_promote(args) -> int:
    """
    승자 정책을 하네스 본체(.claude/policy/)에 반영한다 — **사람 승인 게이트**.

    autoresearch 의 "결과는 가설이지 배포물이 아니다" 를 강제하는 지점이다. `--yes` 없이는
    변경 내용만 보여주고 아무것도 쓰지 않는다.
    """
    led = {r.get("exp"): r for r in _read_ledger()}
    rec = led.get(args.exp)
    if not rec:
        _log(f"❌ {args.exp} 를 원장에서 찾을 수 없다")
        return 1
    if rec.get("outcome") != "KEEP":
        _log(f"❌ {args.exp} 는 {rec.get('outcome')} — KEEP 실험만 승격할 수 있다")
        return 1

    src = _AR / args.exp / "policy"
    files = _policy_files(src)
    _log(f"=== {args.exp} 승격 검토 ===")
    _log(f"  근거: {rec['base']} → {rec['cand']} (delta {rec['delta']}), 거짓 결과 {rec['cand_accuracy']}건")
    _log(f"  대상: {rec['role']}, 시나리오 {','.join(rec['scenarios'])} × {rec['repeats']}회")
    for p in files:
        old = (_PROMOTED / p.name).read_text(encoding="utf-8") if (_PROMOTED / p.name).is_file() else ""
        new = p.read_text(encoding="utf-8")
        if old.strip() == new.strip():
            continue
        _log(f"\n  --- {p.name} ---")
        for l in old.strip().splitlines():
            _log(f"    - {l}")
        for l in new.strip().splitlines():
            _log(f"    + {l}")
    if not args.yes:
        _log("\n⏸ 미반영 — 실제로 적용하려면 `--yes` 를 붙인다 (사람 승인 게이트).")
        _log("   표본이 작으면 재현 실험을 더 돌린 뒤 승격하는 편이 안전하다.")
        return 0

    _PROMOTED.mkdir(parents=True, exist_ok=True)
    for p in files:
        shutil.copy2(p, _PROMOTED / p.name)
    _append_ledger({"exp": args.exp, "outcome": "PROMOTED", "role": rec.get("role"),
                    "by": os.environ.get("USER", "?")})
    _log(f"\n✅ 승격 완료 → {_rel(_PROMOTED)} (커밋은 별도로 하라)")
    return 0


def cmd_self(args) -> int:
    """의존성·경로·불변 매니페스트를 점검한다."""
    ok = True
    _log("=== autoresearch self ===")
    for rel in _IMMUTABLE:
        exists = (_ROOT / rel).is_file()
        ok &= exists
        _log(f"  {'✅' if exists else '❌'} 불변 파일 {rel}")
    suite = _ROOT / "tests" / "suite" / "run_suite.py"
    _log(f"  {'✅' if suite.is_file() else '❌'} 적합도 함수(스위트) {_rel(suite)}")
    _log(f"  {'✅' if _PROGRAM.is_file() else 'ⓘ '} program.md {'있음' if _PROGRAM.is_file() else '없음 (init 필요)'}")
    have_oc = shutil.which("opencode") is not None
    _log(f"  {'✅' if have_oc else '❌'} opencode 실행 파일")
    _log(f"  ⓘ 매니페스트: {json.dumps(_manifest(), ensure_ascii=False)}")
    _log(f"  ⓘ 하네스 본체 정책 주입 경로: {_rel(_PROMOTED)} "
         f"({len(_policy_files(_PROMOTED))}개)")
    return 0 if ok and have_oc else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="autoresearch — 스위트를 적합도 함수로 쓰는 하네스 자가 실험 루프 (localllm 전용)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="program.md + 실험 공간 scaffold")

    p_run = sub.add_parser("run", help="실험 루프 실행 (자동 채택은 원장까지)")
    p_run.add_argument("--experiments", type=int, default=1, help="실험 횟수")
    p_run.add_argument("--scenarios", default="S01,S05", help="시나리오 ID (쉼표 구분)")
    p_run.add_argument("--repeats", type=int, default=1, help="구간당 반복 횟수")
    p_run.add_argument("--timeout", type=int, default=3600, help="구간 제한 시간(초)")
    p_run.add_argument("--budget-min", type=int, default=0, help="전체 예산(분, 0=무제한)")

    sub.add_parser("status", help="원장 요약 + 챔피언 정책")

    p_pr = sub.add_parser("promote", help="승자를 하네스 본체에 반영 (사람 승인 게이트)")
    p_pr.add_argument("exp", help="실험 ID (예: exp-003)")
    p_pr.add_argument("--yes", action="store_true", help="실제로 반영한다")

    sub.add_parser("self", help="의존성·경로 점검")

    args = parser.parse_args()
    sys.exit({"init": cmd_init, "run": cmd_run, "status": cmd_status,
              "promote": cmd_promote, "self": cmd_self}[args.cmd](args))


if __name__ == "__main__":
    main()
