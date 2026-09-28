#!/usr/bin/env python3
"""schema_check.py — 프롬프트의 도구 지시가 실제 스키마와 맞는지 정적 검사한다.

왜 필요한가 (ADR-022 결정 2):
  하네스는 파일 생성에 `edit` 도구를 지목하면서 `content` 를 넘기라고 지시하고 있었다.
  `edit` 스키마에는 `content` 가 없어 **만족 불가능한 지시**였는데, qwen 이 지시를 무시하고
  `write` 를 불러 통과했기 때문에 오래 숨어 있었다. 지시를 문자 그대로 따르는 모델만
  손해를 봤다 (측정 11 결과 13).

  스냅샷에서 지시문을 파생하도록 고쳤지만, 사람이 프롬프트에 도구 이름을 손으로 쓰면
  같은 결함이 재발한다. 이 검사기가 그 재발을 잡는다.

무엇을 검사하는가:
  프롬프트 문자열에서 "<tool> 도구를 불러 <인자>를 넘겨라" 형태를 찾아,
  그 인자가 해당 도구의 properties 에 실재하는지 스냅샷과 대조한다.

한계 (정직하게):
  자연어 프롬프트를 완전 파싱하지 않는다. `Call the X tool with ... <arg> ...` 패턴만 본다.
  이 패턴이 실제 결함이 난 형태이고, 넓히면 오탐이 급증한다 ('name'·'path' 같은 평범한
  영어 단어를 인자로 오인한다 — 실제로 겪었다).

  **미검출 케이스**: 지시문이 f-string 보간으로 조립되면(`f"... {args} ..."`) 인자 이름이
  소스에 문자로 남지 않아 검사가 지나친다. 그런 지점은 스키마에서 파생되므로 애초에
  어긋날 수 없다는 것이 설계상 근거이지만, 검사기가 그것을 **증명하지는 못한다**.

사용:
  python3 .claude/bin/schema_check.py            # 검사 (BLOCK 있으면 exit 1)
  python3 .claude/bin/schema_check.py --list     # 스냅샷 내용 출력
"""
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_SNAPSHOT = _ROOT / ".claude" / "schema" / "opencode-tools.json"
# 도구 지시가 들어가는 파일 (프롬프트를 만드는 곳)
_TARGETS = [
    ".claude/bin/cycle_driver.py",
    ".claude/policy",
    ".opencode/AGENTS.md",
]
# "Call the <tool> tool with <나머지>" — 실제 결함이 난 형태.
# 따옴표 그룹에서 **개행을 빼는 것**이 핵심이다. 예전엔 `[^\"]*` 라 매치가 줄을 넘어
# 22줄·1016자를 삼켰고, 그 안에 있던 **파생 지시(이 기능의 유일한 산출 지점)** 가
# 독립 매치로 방문되지 않았다 — 검사 결과가 윗줄의 따옴표 위상에 달려 있었다.
_CALL = re.compile(r"Call the (\w+) tool with ([^\n\"]*(?:\"[^\n\"]*\"[^\n\"]*)*)")
# ADR-022 결정 1 은 "도구 이름·인자를 직접 타이핑하지 않는다" 인데, 파생은 `write` 한
# 곳뿐이고 나머지는 수기였다 — 그리고 수기 문구들은 위 형식과 달라 **검사 사각**이었다.
# 즉 "S3 결함 0건" 은 검사 가능한 부분집합 위의 0이었다. 형식을 넓혀 사각을 없앤다.
_CALL_ALT = [
    # "Use the write tool to create each file (filePath …, content …)"
    re.compile(r"Use the (\w+) tool[^\n]*"),
    # "The bash tool needs both arguments: command and description."
    re.compile(r"The (\w+) tool (?:needs|requires)[^\n]*"),
]
# `{rel}` 같은 f-string 보간이 든 지시는 **파생 지시**다 — 리터럴 검사 대상이 아니라
# 별도로 센다 (지시를 만드는 코드이지, 지시 그 자체가 아니다).
_INTERP = re.compile(r"[{}]")


def _load() -> dict:
    """스냅샷을 읽는다. 없으면 빈 dict, **손상이면 예외를 올린다**.

    손상을 "없음" 과 같이 취급하면 검사를 조용히 건너뛰고 "결함 0건" 을 찍는다.
    부재는 정상(다른 변형), 손상은 BLOCK 이다 — 구분한다.
    """
    if not _SNAPSHOT.is_file():
        return {}
    return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))


def _joined(text: str) -> str:
    """파이썬 인접 문자열 리터럴을 이어붙인다.

    지시문은 소스에서 여러 줄로 쪼개져 있어도 **모델이 보는 것은 한 문장**이다.
    줄 단위로만 보면 `Use the write tool to create each file "` 에서 끊겨,
    다음 줄의 `filePath`·`content` 를 못 보고 **거짓 BLOCK** 을 낸다.
    닫는 따옴표 + 개행 + 여는 따옴표를 지워 한 줄로 만든다.
    """
    return re.sub(r'"\s*\n\s*"', "", text)


def _sources() -> list[Path]:
    """검사 대상 파일 목록을 모은다."""
    out = []
    for rel in _TARGETS:
        p = _ROOT / rel
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(sorted(f for f in p.rglob("*.md") if f.is_file()))
    return out


def check() -> tuple[list[str], dict]:
    """스키마와 어긋나는 도구 지시를 찾는다.

    Returns:
        (문제 목록, 통계) — 통계에 **무엇을 몇 개 봤는지**를 담는다. 예전엔
        "결함 0건" 만 찍어서, 검사 대상이 0개여도 0개를 봤어도 같은 출력이었다
        (실측: `{"tools": {}}` 일 때 "검사 생략" 과 "결함 0건" 이 연달아 찍혔다).
    """
    stats = {"files": 0, "instructions": 0, "derived": 0}
    try:
        snap = _load()
    except (ValueError, OSError) as exc:
        return ([f"스냅샷 손상 ({_SNAPSHOT.name}): {type(exc).__name__} — "
                 f"재캡처하거나 복구하십시오"], stats)
    if not isinstance(snap, dict):
        return ([f"스냅샷 형태 오류 ({_SNAPSHOT.name}): 최상위가 객체가 아님"], stats)
    tools = snap.get("tools")
    if tools is None:
        print(f"[schema-check] ⓘ 스냅샷 없음 ({_SNAPSHOT.name}) — 검사 생략")
        return ([], stats)
    if not isinstance(tools, dict):
        return ([f"스냅샷 형태 오류: tools 가 객체가 아님 ({type(tools).__name__})"], stats)
    if not tools:
        return ([f"스냅샷의 tools 가 비었습니다 ({_SNAPSHOT.name}) — "
                 f"검사할 기준이 없으므로 결과를 신뢰할 수 없습니다"], stats)

    problems = []
    for src in _sources():
        stats["files"] += 1
        text = _joined(src.read_text(encoding="utf-8"))
        found = list(_CALL.finditer(text))
        for alt in _CALL_ALT:
            found.extend(alt.finditer(text))
        for m in sorted(found, key=lambda x: x.start()):
            if _INTERP.search(m.group(0)):
                stats["derived"] += 1      # 파생 지시 — 리터럴 검사 대상이 아니다
                continue
            stats["instructions"] += 1
            rest = m.group(2) if m.re.groups >= 2 else m.group(0)
            tool = m.group(1)
            spec = tools.get(tool)
            if spec is None:
                problems.append(f"{src.name}: 알 수 없는 도구 '{tool}' 를 지목합니다 "
                                f"(스냅샷에 없음: {sorted(tools)})")
                continue
            # 필수 인자 누락만 본다. "인자가 아닌 것을 넘긴다"는 검사는 오탐이 크다 —
            # 'name'·'path'·'content' 는 평범한 영어 단어라 산문 지시문에 늘 등장한다.
            # 실제 결함(`edit` 를 지목하고 oldString/newString 없이 부르게 한 것)은
            # 필수 인자 누락으로 정확히 잡힌다 (측정 11 결과 13).
            missing = [r for r in (spec.get("required") or [])
                       if not re.search(rf"\b{re.escape(r)}\b", rest)]
            if missing:
                problems.append(
                    f"{src.name}: '{tool}' 도구를 지목하면서 필수 인자 {missing} 가 "
                    f"지시문에 없습니다 — 그대로 따르면 호출이 실패합니다")
    return problems, stats


def main() -> int:
    """검사를 실행하고 결과를 보고한다."""
    if "--list" in sys.argv:
        snap = _load()
        print(f"스냅샷: {_SNAPSHOT}")
        print(f"  캡처: {snap.get('_captured')} / OpenCode {snap.get('_opencode_version')}")
        for name, spec in sorted((snap.get("tools") or {}).items()):
            print(f"  {name:11} required={spec['required']}")
        return 0

    problems, stats = check()
    scope = (f"파일 {stats['files']}개 · 리터럴 지시 {stats['instructions']}건 "
             f"· 파생 지시 {stats['derived']}건")
    if problems:
        print(f"[schema-check] ❌ BLOCK {len(problems)}건 ({scope})")
        for p in problems:
            print(f"  - {p}")
        return 1
    if stats["instructions"] == 0:
        # "검사했는데 결함이 없다" 와 "아무것도 안 봤다" 는 다른 주장이다.
        print(f"[schema-check] ⓘ 검사 대상 지시가 없습니다 ({scope}) — S3 판정 불가")
        return 0
    print(f"[schema-check] ✅ 도구 지시가 스키마와 일치합니다 ({scope}, S3: 결함 0건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
