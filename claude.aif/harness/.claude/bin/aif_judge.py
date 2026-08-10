#!/usr/bin/env python3
"""
aif_judge — 항목형 rubric 판정 엔진 (AIF 오버레이, ADR-020).

judge 에게 "종합 판단"을 묻는 대신 **항목별 이진 판정 + 증거**를 요구하고, 그 판정을
결정론적으로 검증·앙상블한다. RLAIF/CAI 문헌의 판정 설계 규율 3개를 이식한 것이다:

| 문헌 | 이 스크립트 |
|---|---|
| Rubrics-as-Rewards — 구조화 채점표가 약한 judge 의 정렬을 개선하고 **분산을 줄인다** | 항목별 판정 + 증거 강제 |
| CAI — 16원칙 **앙상블**로 preference model 점수 안정화 | `--repeats N` 항목별 다수결 |
| CAI — CoT judge 확률이 0/1 로 붕괴 → **40–60% 클램프** | 표가 갈린 항목은 `UNCERTAIN` (억지 판정 금지) |
| RLAIF — position bias 18~56% → 순서 교대 | `compare` 의 양방향 판정 불일치 검출 |

**이 스크립트는 모델을 호출하지 않는다** (`auto` 모드 예외). 호스트(에이전트)가 판정하고,
스크립트는 프롬프트를 만들고 돌아온 판정을 검증·집계한다 — verify_loop 와 같은 역할 분담이다.

사용:
    python3 .claude/bin/aif_judge.py plan code-review --target src/auth.py,tests/ --repeats 3
    python3 .claude/bin/aif_judge.py record code-review --run F001-r1 < judgment.txt
    python3 .claude/bin/aif_judge.py aggregate F001-r1
    python3 .claude/bin/aif_judge.py compare code-review --a before.py --b after.py
    python3 .claude/bin/aif_judge.py auto code-review --target src/auth.py --repeats 3   # 로컬 LLM 변형
    python3 .claude/bin/aif_judge.py self
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

_BIN = Path(__file__).resolve().parent
_ROOT = _BIN.parent.parent
_RUBRICS = _ROOT / ".claude" / "rubrics"
_STATE = _ROOT / ".claude" / "state" / "aif"

_VERDICTS = ("met", "unmet", "na")
_PATH_LINE = re.compile(r"[\w./-]+:\d+")
_QUOTED = re.compile(r"[\"'`].{4,}[\"'`]")
_ITEM_HEADER = re.compile(r"^###\s+(\w+)\s*\|\s*(MUST|SHOULD)\s*\|\s*(.+?)\s*$")
_ANSWER = re.compile(r"^\s*[-*]?\s*(\w+)\s*:\s*(met|unmet|na)\b(.*)$", re.I)


def _log(msg: str) -> None:
    print(msg, flush=True)


# ─────────────────────────────── rubric 파싱 ────────────────────────────────

def parse_items(name: str) -> list[dict]:
    """
    `<name>.items.md` 를 파싱해 항목 목록을 반환한다.

    Args:
        name: rubric 이름 (예: "code-review")

    Returns:
        [{"id","sev","title","req","ev","rule"}, ...] — 파일이 없으면 빈 목록
    """
    p = _RUBRICS / f"{name}.items.md"
    if not p.is_file():
        return []
    items: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        m = _ITEM_HEADER.match(line)
        if m:
            items.append({"id": m.group(1), "sev": m.group(2), "title": m.group(3),
                          "req": "", "ev": "", "rule": "", "evtype": "위치"})
            continue
        if not items:
            continue
        for key, prefix in (("req", "요구:"), ("ev", "증거:"), ("rule", "판정:"),
                            ("evtype", "증거유형:")):
            if line.startswith(prefix):
                items[-1][key] = line[len(prefix):].strip()
    return items


def build_prompt(name: str, items: list[dict], target: str, context: str = "") -> str:
    """
    판정 프롬프트를 만든다 (항목·요구·증거 + 판정 대상 내용 + 출력 형식).

    `context` 에 대상 파일 내용을 넣어야 한다. 파일명만 주면 모델이 도구로 파일을 읽으려
    시도하다 실패하고 산문을 반환한다 (측정 10 — 첫 A/B 에서 판정 100% 무효의 원인).
    판정은 **주어진 내용만으로** 하게 하고 도구 사용을 금지한다.
    """
    lines = [f"{it['id']} ({it['sev']}) {it['title']}\n"
             f"    요구: {it['req']}\n    증거: {it['ev']}"
             + ("  [부재 항목 — 확인한 범위를 서술하라]" if it.get("evtype", "").startswith("부재") else "")
             + (f"\n    판정: {it['rule']}" if it["rule"] else "")
             for it in items]
    ids = ", ".join(it["id"] for it in items)
    body = context.strip() or "(대상 내용이 제공되지 않았다 — 확인 불가 항목은 unmet 으로 판정하라)"
    return (
        f"RUBRIC 판정 — {name}\n"
        f"대상: {target}\n\n"
        "Judge from the content below only. Do NOT use any tool (no file read, no web fetch) — "
        "everything you need is in this prompt.\n\n"
        f"===== 판정 대상 내용 =====\n{body}\n===== 내용 끝 =====\n\n"
        "아래 각 항목을 위 내용에서 확인하고 항목마다 정확히 한 줄로 판정하라.\n\n"
        + "\n".join(lines) + "\n\n"
        "출력 형식 (다른 텍스트 없이 이 줄들만):\n"
        "<항목id>: <met|unmet|na> | <증거> | <인용(선택)>\n\n"
        f"규칙:\n"
        f"- {len(items)}개 항목({ids})을 각각 정확히 한 번 판정한다.\n"
        "- met 으로 판정하려면 `파일:행` 또는 실제 출력·코드의 인용을 증거로 제시한다.\n"
        "  증거를 제시할 수 없으면 met 이 아니다.\n"
        "- na 는 항목이 대상에 적용되지 않을 때만 쓰고, 사유를 적는다.\n"
        "- rubric 의 '증거:' 문구를 그대로 옮겨 적는 것은 증거가 아니다.\n"
    )


def _read_target(target: str) -> str:
    """`--target` 의 쉼표 구분 경로들을 읽어 판정 대상 내용을 만든다 (없는 파일은 표시)."""
    chunks = []
    for name in (t.strip() for t in target.split(",") if t.strip()):
        p = _ROOT / name
        body = p.read_text(encoding="utf-8") if p.is_file() else "(파일 없음)"
        chunks.append(f"--- {name} ---\n{body}")
    return "\n".join(chunks)


# ─────────────────────────────── 판정 검증 ────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def validate(items: list[dict], raw: str) -> dict:
    """
    judge 가 반환한 텍스트를 검증한다.

    항목 누락·중복·미정의 id 는 판정 전체를 무효(INVALID)로 만든다. 개별 항목의 증거 결함
    (증거 부재 / rubric 에코 / na 사유 부재)은 그 항목만 무효 처리해 `UNCERTAIN` 으로 남긴다 —
    추측으로 채우면 판정 자체가 신뢰를 잃기 때문이다.

    Returns:
        {"valid": bool, "reason": str, "items": {id: {"verdict","evidence","invalid"}}}
    """
    by_id = {it["id"]: it for it in items}
    found: dict[str, dict] = {}
    dups: list[str] = []
    unknown: list[str] = []

    for line in raw.splitlines():
        m = _ANSWER.match(line)
        if not m:
            continue
        iid, verdict = m.group(1), m.group(2).lower()
        if iid not in by_id:
            unknown.append(iid)
            continue
        if iid in found:
            dups.append(iid)
            continue
        parts = [p.strip() for p in m.group(3).split("|") if p.strip()]
        evidence = " | ".join(parts)
        rec = {"verdict": verdict, "evidence": evidence, "invalid": ""}

        if verdict == "met":
            # 부재 항목("자격증명 없음" 등)은 원리상 파일:행 증거가 불가능하다 — 대신 어떤 범위를
            # 확인했는지 서술을 요구한다 (측정 10: 위치 증거를 강요하면 상시 UNCERTAIN 이 된다).
            absence = by_id[iid].get("evtype", "위치").startswith("부재")
            floor = 20 if absence else 12
            if len(evidence) < floor:
                rec["invalid"] = "증거 부재 또는 과소"
            elif not absence and not (_PATH_LINE.search(evidence) or _QUOTED.search(evidence)):
                rec["invalid"] = "파일:행 또는 인용 증거 없음"
            elif _norm(by_id[iid]["ev"])[:15] and _norm(evidence).startswith(_norm(by_id[iid]["ev"])[:15]):
                rec["invalid"] = "rubric 증거 문구 에코"
        elif verdict == "na" and len(evidence) < 5:
            rec["invalid"] = "na 사유 부재"
        found[iid] = rec

    missing = [i for i in by_id if i not in found]
    if missing or dups or unknown:
        problems = []
        if missing:
            problems.append(f"누락 {missing}")
        if dups:
            problems.append(f"중복 {dups}")
        if unknown:
            problems.append(f"미정의 id {unknown}")
        return {"valid": False, "reason": "; ".join(problems), "items": found}
    return {"valid": True, "reason": "", "items": found}


def aggregate(items: list[dict], judgments: list[dict]) -> dict:
    """
    N회 판정을 항목별 다수결로 앙상블한다.

    유효표가 과반에 못 미치거나 최다표가 동수면 그 항목은 `UNCERTAIN` 이다. 전체 판정은
    MUST 기준으로 revision > uncertain > pass 순으로 결정된다 (추측하지 않고 에스컬레이션).
    """
    need = len(judgments) // 2 + 1
    per: dict[str, dict] = {}
    for it in items:
        votes = [j["items"][it["id"]] for j in judgments
                 if j.get("valid") and it["id"] in j["items"] and not j["items"][it["id"]]["invalid"]]
        counts = Counter(v["verdict"] for v in votes)
        top = counts.most_common(2)
        if len(votes) < need or not top:
            decided, why = "UNCERTAIN", f"유효표 {len(votes)}/{len(judgments)} (과반 {need} 미달)"
        elif len(top) > 1 and top[0][1] == top[1][1]:
            decided, why = "UNCERTAIN", f"동수 {dict(counts)}"
        else:
            decided, why = top[0][0], f"{dict(counts)}"
        per[it["id"]] = {
            "sev": it["sev"], "title": it["title"], "decided": decided, "tally": why,
            "evidence": next((v["evidence"] for v in votes if v["verdict"] == decided), ""),
        }

    must = [v for v in per.values() if v["sev"] == "MUST"]
    if any(v["decided"] == "unmet" for v in must):
        overall = "revision"
    elif any(v["decided"] == "UNCERTAIN" for v in must):
        overall = "uncertain"
    else:
        overall = "pass"
    return {"overall": overall, "items": per,
            "judgments": len(judgments),
            "invalid_judgments": sum(1 for j in judgments if not j.get("valid"))}


# ─────────────────────────────── 서브커맨드 ────────────────────────────────

def cmd_plan(args) -> int:
    """판정 프롬프트를 출력한다 (호스트가 이걸 judge 에게 준다)."""
    items = parse_items(args.rubric)
    if not items:
        _log(f"❌ rubric 항목 없음 — {_RUBRICS / (args.rubric + '.items.md')}")
        return 1
    _log(build_prompt(args.rubric, items, args.target, _read_target(args.target)))
    if args.repeats > 1:
        _log(f"\n# 위 프롬프트를 {args.repeats}회 독립 실행한 뒤 각각 record 하고 aggregate 한다.")
    return 0


def cmd_record(args) -> int:
    """judge 판정을 검증해 저장한다 (입력: 파일 또는 stdin)."""
    items = parse_items(args.rubric)
    if not items:
        _log(f"❌ rubric 항목 없음 — {args.rubric}")
        return 1
    raw = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    res = validate(items, raw)
    d = _STATE / args.run
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob("j*.json"))) + 1
    res["rubric"] = args.rubric
    (d / f"j{n}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    if not res["valid"]:
        _log(f"⚠️ 판정 {n} 무효 — {res['reason']} (집계에서 제외된다)")
    else:
        bad = {i: r["invalid"] for i, r in res["items"].items() if r["invalid"]}
        _log(f"✅ 판정 {n} 기록 ({len(res['items'])}항목)" + (f" — 증거 결함 {bad}" if bad else ""))
    return 0


def cmd_aggregate(args) -> int:
    """저장된 판정들을 앙상블해 최종 verdict 를 낸다."""
    d = _STATE / args.run
    files = sorted(d.glob("j*.json")) if d.is_dir() else []
    if not files:
        _log(f"❌ 판정 기록 없음 — {d}")
        return 1
    judgments = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    items = parse_items(judgments[0].get("rubric", args.rubric or ""))
    if not items:
        _log("❌ rubric 항목을 찾을 수 없다 — --rubric 으로 지정하라")
        return 1

    agg = aggregate(items, judgments)
    (d / "verdict.json").write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")

    mark = {"met": "✅", "unmet": "❌", "na": "—", "UNCERTAIN": "❔"}
    _log(f"=== {args.run} — 판정 {agg['judgments']}회 (무효 {agg['invalid_judgments']}) ===")
    for iid, v in agg["items"].items():
        _log(f"  {mark[v['decided']]} {iid} ({v['sev']}) {v['title']} — {v['tally']}")
        if v["decided"] == "unmet" and v["evidence"]:
            _log(f"       근거: {v['evidence'][:160]}")
    _log(f"\n최종: **{agg['overall']}**")
    rubric = judgments[0].get("rubric", "")
    if agg["overall"] == "uncertain":
        # verify_loop 는 pass|revision|fail 만 받는다. 갈린 판정을 그중 하나로 강제 기록하면
        # 불확실성이 기록에서 사라진다 — 반복을 늘려 해소하거나 사람이 판단한다.
        unsure = [i for i, v in agg["items"].items() if v["decided"] == "UNCERTAIN"]
        _log(f"  판정이 갈린 항목: {unsure} — 억지로 정하지 않는다.")
        _log(f"  해소: aif_judge.py plan {rubric} 을 더 실행해 record 후 재집계, 또는 사람이 해당 항목만 확인.")
    else:
        _log(f"\n기록: python3 .claude/bin/verify_loop.py record <F> --grader {rubric} "
             f"--verdict {agg['overall']}")
    return 0


def cmd_compare(args) -> int:
    """순서를 교대한 두 개의 비교 프롬프트를 출력한다 (position bias 검출)."""
    items = parse_items(args.rubric)
    if not items:
        _log(f"❌ rubric 항목 없음 — {args.rubric}")
        return 1
    for first, second, tag in ((args.a, args.b, "AB"), (args.b, args.a, "BA")):
        _log(f"\n===== 순서 {tag} =====")
        _log(build_prompt(args.rubric, items, f"후보1={first}, 후보2={second}",
                          _read_target(f"{first},{second}")))
    _log("\n# 두 순서의 판정이 다르면 그 항목은 position bias 로 오염된 것이다 → UNCERTAIN 처리.")
    _log("# RLAIF 실측: 순서 편향이 큰 모델 18%, 작은 모델 56%.")
    return 0


def cmd_auto(args) -> int:
    """로컬 LLM 으로 판정을 N회 자동 수행한다 (cycle_driver 보유 변형 전용)."""
    items = parse_items(args.rubric)
    if not items:
        _log(f"❌ rubric 항목 없음 — {args.rubric}")
        return 1
    sys.path.insert(0, str(_BIN))
    try:
        import cycle_driver as cd
    except ImportError:
        _log("ⓘ auto 모드는 cycle_driver(d-2 오버레이)가 있는 변형에서만 동작한다.")
        _log("  다른 변형에서는 plan → (호스트 judge) → record → aggregate 로 쓴다.")
        return 2

    prompt = build_prompt(args.rubric, items, args.target, _read_target(args.target))
    model = cd._role_models().get(args.role)
    d = _STATE / args.run
    d.mkdir(parents=True, exist_ok=True)
    for i in range(1, args.repeats + 1):
        rc, out = cd._opencode_run(None, prompt, model=model)
        res = validate(items, out)
        res["rubric"] = args.rubric
        (d / f"j{i}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        _log(f"  판정 {i}/{args.repeats}: {'유효' if res['valid'] else '무효 — ' + res['reason']}")
    return cmd_aggregate(args)


def cmd_self(args) -> int:
    """rubric 항목 파싱과 상태 경로를 점검한다."""
    ok = True
    _log("=== aif_judge self ===")
    for name in sorted(p.stem.replace(".items", "") for p in _RUBRICS.glob("*.items.md")):
        items = parse_items(name)
        must = sum(1 for i in items if i["sev"] == "MUST")
        good = bool(items) and all(i["req"] and i["ev"] for i in items)
        ok &= good
        _log(f"  {'✅' if good else '❌'} {name}: {len(items)}항목 (MUST {must}) "
             f"{'' if good else '— 요구/증거 누락 항목 있음'}")
    if not list(_RUBRICS.glob("*.items.md")):
        _log("  ❌ 항목형 rubric 이 없다 (.claude/rubrics/*.items.md)")
        ok = False
    _log(f"  ⓘ 판정 기록 경로: {_STATE.relative_to(_ROOT)}")
    have_cd = (_BIN / "cycle_driver.py").is_file()
    _log(f"  {'✅' if have_cd else 'ⓘ '} auto 모드 {'가능' if have_cd else '불가 (cycle_driver 없음 — plan/record/aggregate 로 사용)'}")
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="aif_judge — 항목형 rubric 판정 (증거 강제 · 앙상블 · UNCERTAIN)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pl = sub.add_parser("plan", help="판정 프롬프트 생성")
    p_pl.add_argument("rubric")
    p_pl.add_argument("--target", default="(대상 미지정)")
    p_pl.add_argument("--repeats", type=int, default=1)

    p_re = sub.add_parser("record", help="judge 판정 검증·저장 (stdin 또는 --file)")
    p_re.add_argument("rubric")
    p_re.add_argument("--run", required=True, help="판정 묶음 id (예: F001-r1)")
    p_re.add_argument("--file", help="판정 텍스트 파일 (생략 시 stdin)")

    p_ag = sub.add_parser("aggregate", help="앙상블 집계 → 최종 verdict")
    p_ag.add_argument("run")
    p_ag.add_argument("--rubric", help="기록에 rubric 이 없을 때 지정")

    p_cp = sub.add_parser("compare", help="순서 교대 비교 프롬프트 (position bias 검출)")
    p_cp.add_argument("rubric")
    p_cp.add_argument("--a", required=True)
    p_cp.add_argument("--b", required=True)

    p_au = sub.add_parser("auto", help="로컬 LLM 자동 판정 (cycle_driver 보유 변형)")
    p_au.add_argument("rubric")
    p_au.add_argument("--target", default="(대상 미지정)")
    p_au.add_argument("--run", required=True)
    p_au.add_argument("--repeats", type=int, default=3)
    p_au.add_argument("--role", default="reviewer")

    sub.add_parser("self", help="rubric 파싱·경로 점검")

    args = parser.parse_args()
    sys.exit({"plan": cmd_plan, "record": cmd_record, "aggregate": cmd_aggregate,
              "compare": cmd_compare, "auto": cmd_auto, "self": cmd_self}[args.cmd](args))


if __name__ == "__main__":
    main()
