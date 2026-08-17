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
# "Call the <tool> tool with <나머지>" — 실제 결함이 난 형태
_CALL = re.compile(r"Call the (\w+) tool with ([^\n\"]*(?:\"[^\"]*\"[^\n\"]*)*)")


def _load() -> dict:
    """스냅샷을 읽는다. 없으면 검사를 건너뛴다 (하네스 동작에 영향 없음)."""
    if not _SNAPSHOT.is_file():
        return {}
    return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))


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


def check() -> list[str]:
    """스키마와 어긋나는 도구 지시를 찾아 문제 목록을 반환한다."""
    snap = _load()
    tools = snap.get("tools") or {}
    if not tools:
        print(f"[schema-check] ⓘ 스냅샷 없음 ({_SNAPSHOT.name}) — 검사 생략")
        return []

    problems = []
    for src in _sources():
        text = src.read_text(encoding="utf-8")
        for m in _CALL.finditer(text):
            tool, rest = m.group(1), m.group(2)
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
    return problems


def main() -> int:
    """검사를 실행하고 결과를 보고한다."""
    if "--list" in sys.argv:
        snap = _load()
        print(f"스냅샷: {_SNAPSHOT}")
        print(f"  캡처: {snap.get('_captured')} / OpenCode {snap.get('_opencode_version')}")
        for name, spec in sorted((snap.get("tools") or {}).items()):
            print(f"  {name:11} required={spec['required']}")
        return 0

    problems = check()
    if not problems:
        print("[schema-check] ✅ 도구 지시가 스키마와 일치합니다 (S3: 결함 0건)")
        return 0
    print(f"[schema-check] ❌ BLOCK {len(problems)}건")
    for p in problems:
        print(f"  - {p}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
