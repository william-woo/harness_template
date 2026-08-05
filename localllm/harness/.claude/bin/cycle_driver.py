#!/usr/bin/env python3
"""
cycle_driver.py — 로컬 결정론 supervisor: SDLC 사이클 상태 기계 (localllm 전용, d-2)

측정 05/06 의 결론을 코드화한다 (ADR-018):
  - LLM 이 문맥으로 흐름을 조율(G5)하는 것은 32B 도 실패 → **흐름은 코드가 소유**
  - 로컬 LLM 은 역할 단위로만 호출: developer(생성, 14B) / reviewer·qa(판정, 32B)
  - 값 전달은 전부 드라이버가 파일·인자로 주입 (LLM 문맥 전달 배제)
  - grader 는 결정론 (테스트 실행 + 기대 출력 확인 — 공허 통과 차단)
  - 재작업 지시는 전체 파일 재작성 + 실패 출력 + 현재 파일 내용 주입 (AGENTS.md 규칙 6)
  - 판정 역할은 bash-only 파일 접근 (AGENTS.md 규칙 7) + 기록 여부를 드라이버가 검증
  - verify-loop 상태로 유계 재시도 — 에스컬레이션 도달 시 상위 호스트로 인계 (exit 2)

이로써 supervisor(핸드오프·grader·북키핑)가 **로컬 머신에서 무인 실행**된다.
상위 호스트(Claude Code/사람)는 에스컬레이션 시에만 개입한다.

사용법:
  python3 .claude/bin/cycle_driver.py run F001 \
      --test-cmd "python3 test_fizzbuzz.py" --expect PASS \
      --files fizzbuzz.py,test_fizzbuzz.py
  python3 .claude/bin/cycle_driver.py self       # 의존성 점검 (opencode/모델/verify_loop)

외부 의존성: OpenCode CLI (d-2 실행 환경) — 미설치 시 안내 후 exit 0 (graceful degrade).
드라이버 자체는 Python stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    """하네스 루트를 반환한다 (스크립트 위치 기준 — session_search.py 와 동일 규약)."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent


_ROOT = _project_root()
_VL = _ROOT / ".claude" / "bin" / "verify_loop.py"
_STATE_DIR = _ROOT / ".claude" / "state" / "verify-loop"
_OC_TIMEOUT = int(os.environ.get("CYCLE_OC_TIMEOUT", "420"))
# --agent 경로 건강 상태 (측정 08: 시간대 단위로 불안정 — 실패하면 주입 모드로 고정)
_AGENT_PATH_HEALTHY = True


def _log(msg: str) -> None:
    """드라이버 진행 로그를 출력한다 (단계 prefix 규약)."""
    print(f"[cycle-driver] {msg}", flush=True)


def _is_transient(rc: int, out: str) -> bool:
    """
    OpenCode 호스트의 일시적 실패인지 판별한다 (측정 08).

    두 실패 양상이 실측됐다: ① 부트스트랩 행(timeout) ② 서버 즉시 실패
    (`UnknownError` / "Unexpected server error", 수십 ms). 후자는 exit code 만 보면
    정상 종료와 구분되지 않아 판정 미기록으로 오인됐다 — 출력 시그니처로 함께 판별한다.
    """
    if rc != 0:
        return True
    sig = ("UnknownError", "Unexpected server error", "Check server logs")
    return any(s in out for s in sig)


class _HostLock:
    """
    OpenCode 인스턴스를 머신 단위로 직렬화하는 파일 락 (측정 08).

    실측: 같은 데이터 디렉토리(~/.local/share/opencode)를 공유하는 opencode 인스턴스가
    동시에 뜨면 `createUserMessage` 가 UnknownError 로 즉시 실패한다. 드라이버 여러 개나
    사람이 병행 사용하는 상황에서 사이클이 무더기로 무산되므로 호출 구간을 직렬화한다.
    락 획득 실패(타임아웃)는 진행을 막지 않고 경고만 남긴다 — hook-failure-tolerance 정신.
    """

    def __init__(self, timeout: int = 900):
        self.path = Path(os.environ.get("CYCLE_OC_LOCK", "/tmp/harness-opencode.lock"))
        self.timeout = timeout
        self._fh = None

    def __enter__(self):
        import fcntl
        import time as _t
        deadline = _t.monotonic() + self.timeout
        self._fh = self.path.open("a+")
        while True:
            try:
                fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if _t.monotonic() >= deadline:
                    _log("  ⚠️ opencode 락 대기 초과 — 직렬화 없이 진행 (동시 실행 위험)")
                    return self
                _t.sleep(2)

    def __exit__(self, *exc):
        import fcntl
        if self._fh:
            try:
                fcntl.flock(self._fh, fcntl.LOCK_UN)
            finally:
                self._fh.close()
                self._fh = None
        return False


def _opencode_run(agent: str | None, prompt: str, model: str | None = None,
                  attempts: int | None = None) -> tuple[int, str]:
    """
    opencode run 을 실행한다. 호스트 일시 실패(행/즉시 에러)에 지수 백오프로 재시도하고,
    머신 단위 락으로 인스턴스를 직렬화한다 (동시 실행 충돌 방지 — 측정 08).

    Returns:
        (returncode, 표준출력+표준에러 결합 텍스트). 모든 시도가 일시 실패면 (124, 마지막 출력).
    """
    import tempfile
    import time

    cmd = ["opencode", "run"]
    # `--pure` 는 쓰지 않는다 (측정 08): --agent 와 조합하면 에이전트 지정 호출이 100% 실패했다.
    # 측정 07 에서 `--pure` 를 넣은 근거(부트스트랩 행)는 같은 업스트림 간헐 결함이었고,
    # 실측 결과 --pure 는 그 결함을 줄이지 못하면서 에이전트 경로만 깨뜨렸다.
    # (CYCLE_OC_PURE=1 로 명시 opt-in 만 허용 — 진단용.)
    if os.environ.get("CYCLE_OC_PURE", "0") == "1":
        cmd.append("--pure")
    if agent:
        cmd += ["--agent", agent]
    if model:
        cmd += ["-m", model]
    cmd.append(prompt)

    if attempts is None:
        attempts = int(os.environ.get("CYCLE_OC_ATTEMPTS", "5"))
    backoffs = [5, 15, 30, 60]
    iso_dir: str | None = None
    last_out = ""
    for attempt in range(1, attempts + 1):
        env = dict(os.environ)
        # 중요 (측정 08): OpenCode 는 상대경로를 PWD 기준으로 해석한다. subprocess 의 cwd=
        # 만으로는 PWD 가 부모 값으로 남아 산출 파일이 상위 디렉토리에 떨어진다.
        env["PWD"] = str(_ROOT)
        if iso_dir:
            env["XDG_DATA_HOME"] = iso_dir
        try:
            with _HostLock():
                r = subprocess.run(
                    cmd, cwd=_ROOT, capture_output=True, text=True,
                    timeout=_OC_TIMEOUT, env=env,
                )
            rc, out = r.returncode, (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired:
            rc, out = 124, f"timeout {_OC_TIMEOUT}s"
        last_out = out
        if not _is_transient(rc, out):
            return rc, out
        reason = "timeout" if rc == 124 else "서버 즉시 실패"
        if attempt >= attempts:
            _log(f"  ⚠️ opencode {reason} — {attempts}회 모두 실패")
            break
        # 3번째 시도부터 데이터 디렉토리를 격리한다 (측정 08: 새 DB 에서는 정상 동작 관측).
        # 공유 DB 의 상태 경합이 원인일 때 사이클을 살리는 폴백 — 그 실행의 세션 recall 만 분리된다.
        if attempt >= 2 and iso_dir is None:
            iso_dir = tempfile.mkdtemp(prefix="harness-oc-data-")
            _log(f"  ↺ 데이터 디렉토리 격리 폴백 적용: {iso_dir}")
        backoff = backoffs[min(attempt - 1, len(backoffs) - 1)]
        _log(f"  ⚠️ opencode {reason} — {backoff}초 후 재시도 ({attempt}/{attempts})")
        time.sleep(backoff)
    return 124, last_out


def _role_prompt(role: str) -> str | None:
    """
    주입 모드용 **컴팩트 역할 브리프**를 반환한다.

    측정 08 라운드 6: `.opencode/agent/<role>.md` 본문 전체(2.4KB)를 주입하면 14B 가 도구를
    호출하지 않고 설명만 반환해 파일이 생성되지 않았다. frontmatter `description`(1~3줄)만
    쓰면 역할 정체성은 유지하면서 지시가 짧아져 도구 호출이 정상 동작한다.
    (본문이 이미 짧으면(<800자) 본문을 쓴다 — 정보 손실 최소화.)
    """
    md = _ROOT / ".opencode" / "agent" / f"{role}.md"
    if not md.is_file():
        return None
    raw = md.read_text(encoding="utf-8")
    body, desc = raw.strip(), ""
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm, body = parts[1], parts[2].strip()
            lines, collecting = [], False
            for ln in fm.splitlines():
                if ln.startswith("description:"):
                    collecting = True
                    inline = ln.split(":", 1)[1].strip()
                    if inline and inline not in (">-", "|", ">", "|-"):
                        lines.append(inline)
                    continue
                if collecting:
                    if ln[:1] not in (" ", "\t") and ln.strip():
                        break
                    if ln.strip():
                        lines.append(ln.strip())
            desc = " ".join(lines).strip()
    if len(body) < 800:
        return body
    return desc or body[:800]


def _agent_call(role: str, task: str) -> tuple[int, str]:
    """
    역할 에이전트를 호출한다. `--agent` 경로가 실패하면 역할 프롬프트 주입으로 폴백한다.

    측정 08: 이 환경의 OpenCode 는 커스텀(마크다운) 에이전트 실행이 시간대 단위로 불안정하다
    (내용·경로·DB 무관, 실패는 0.6초 내 즉시). 같은 구간에서도 `-m <model>` + 역할 프롬프트
    주입은 100% 동작하므로, 호스트가 건강할 때는 `--agent`(권한 deny-list 강제 유지)를 쓰고
    실패하면 주입 모드로 사이클을 이어간다.

    폴백 모드의 한계: 도구 권한이 호스트에서 강제되지 않는다 (역할 규율은 프롬프트로만).
    """
    global _AGENT_PATH_HEALTHY
    if _AGENT_PATH_HEALTHY:
        # 저비용 프로브: 이 경로의 실패는 0.6초 내 즉시 드러나므로 1회만 시도한다.
        rc, out = _opencode_run(role, task, attempts=1)
        if rc != 124:
            return rc, out
        _AGENT_PATH_HEALTHY = False   # sticky — 이번 실행 동안 --agent 재시도 안 함
        _log("  ⓘ --agent 경로 비정상 판정 — 이번 실행은 주입 모드로 고정")

    preamble = _role_prompt(role)
    model = _role_models().get(role)
    if not preamble or not model:
        _log(f"  ⚠️ {role} 주입 불가 (역할 정의/모델 매핑 부재) — --agent 로 재시도")
        return _opencode_run(role, task)

    _log(f"  ↺ {role} 주입 모드: 역할 프롬프트 + {model.split('/')[-1]} "
         f"(호스트 권한 강제 없음 — 프롬프트 규율만)")
    combined = (
        f"ROLE ({role}): {preamble[:900]}\n\n"
        "TOOL RULES: do the work with tools now. Use the edit tool for each file "
        "(relative path like 'foo.py', never a leading slash), and the bash tool to run "
        "commands. Explaining or printing code is not enough — the files must exist on disk.\n\n"
        f"TASK: {task}"
    )
    return _opencode_run(None, combined, model=model)


def _vl(args: list[str]) -> str:
    """verify_loop.py 서브커맨드를 실행하고 출력을 반환한다."""
    r = subprocess.run(
        [sys.executable, str(_VL)] + args, cwd=_ROOT, capture_output=True, text=True
    )
    return (r.stdout or "") + (r.stderr or "")


def _vl_state(feature: str) -> dict:
    """verify-loop 상태 JSON 을 읽는다 (없으면 빈 dict)."""
    p = _STATE_DIR / f"{feature}.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _judge_recorded(feature: str, grader: str, before_n: int) -> str | None:
    """judge 가 새 판정을 기록했는지 검증한다. 기록됐으면 verdict, 아니면 None."""
    for a in _vl_state(feature).get("attempts", []):
        if a.get("n", 0) > before_n and a.get("grader") == grader:
            return a.get("verdict")
    return None


def _grade(test_cmd: str, expect: str | None) -> tuple[bool, str]:
    """결정론 grader: 테스트 명령 실행 — exit 0 + 기대 출력 확인 (공허 통과 차단)."""
    r = subprocess.run(
        test_cmd, shell=True, cwd=_ROOT, capture_output=True, text=True, timeout=120
    )
    out = (r.stdout or "") + (r.stderr or "")
    ok = r.returncode == 0 and (expect is None or expect in out)
    return ok, out.strip()[-800:]


def _files_context(files: list[str]) -> str:
    """재작업 프롬프트에 주입할 현재 파일 내용을 구성한다 (드라이버가 값 주입 — LLM 문맥 전달 배제)."""
    chunks = []
    for f in files:
        p = _ROOT / f
        body = p.read_text(encoding="utf-8") if p.is_file() else "(파일 없음)"
        chunks.append(f"--- current content of {f} ---\n{body}")
    return "\n".join(chunks)


def _resolvable_models() -> set[str]:
    """`opencode models` 가 해석 가능한 모델 집합을 반환한다 (실패 시 빈 집합)."""
    try:
        r = subprocess.run(["opencode", "models"], cwd=_ROOT, capture_output=True,
                           text=True, timeout=90)
        return {ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()}
    except Exception:
        return set()


def _role_models() -> dict[str, str]:
    """프로젝트 opencode.json 의 역할별 모델 매핑을 반환한다."""
    p = _ROOT / "opencode.json"
    if not p.is_file():
        return {}
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    out = {}
    for role, spec in (cfg.get("agent") or {}).items():
        m = (spec or {}).get("model")
        if m:
            out[role] = m
    return out


def _preflight() -> list[str]:
    """
    역할별 모델이 실제로 해석 가능한지 점검한다 (측정 08 근본 원인 가드).

    OpenCode 는 프로젝트 opencode.json 의 provider.models 를 모델 해석에 반영하지 않으므로,
    역할 모델이 전역 설정에 없으면 --agent 실행 전체가 UnknownError 로 실패한다.
    미해석 모델을 조기에 찾아 실행 전에 알린다 (차단하지 않음 — 안내 후 진행).
    """
    resolvable = _resolvable_models()
    if not resolvable:
        return []
    missing = [f"{role}={m}" for role, m in _role_models().items() if m not in resolvable]
    if missing:
        _log("⚠️ 프리플라이트: 해석 불가 역할 모델 — 전역 설정(~/.config/opencode)에 등재 필요")
        _log(f"   {missing}")
        _log("   해결: bash .claude/bin/opencode-setup.sh (누락 모델 병합)")
    return missing


_DEFECT_HINTS = ("missing", "incorrect", "wrong", "not implemented", "does not",
                 "should be", "bug", "누락", "없음", "잘못")


def _mechanical_findings(files: list[str]) -> list[str]:
    """
    기계적으로 확인 가능한 결함을 수집한다 (judge 프롬프트에 사전 제시용).

    측정 08: judge 가 docstring 부재를 인지하면서도 pass 를 기록했다. 결정론적으로 검출
    가능한 항목은 미리 제시해 판정 근거를 좁힌다 (coding-standards 가 docstring 을 요구).
    """
    out: list[str] = []
    for rel in files:
        fp = _ROOT / rel
        if not fp.is_file() or not rel.endswith(".py"):
            continue
        base = rel.split("/")[-1]
        # 테스트 파일은 docstring 요구 대상이 아니다 (코딩 표준·AC 모두 요구하지 않음).
        # 이를 제시하면 judge 가 과도하게 revision 을 낸다 (라운드 11 S08/S09 오탐).
        if base.startswith("test_") or base.endswith("_test.py"):
            continue
        body = fp.read_text(encoding="utf-8", errors="replace")
        pat = r"^def\s+(\w+)\s*\([^)]*\)\s*:\s*\n(\s+)(\S.*)$"
        for m in re.finditer(pat, body, re.MULTILINE):
            name, first = m.group(1), m.group(3).lstrip()
            starts_doc = first.startswith('"""') or first.startswith("'''")
            if not starts_doc and not name.startswith("_") and not name.startswith("test_"):
                out.append(f"{rel}: 함수 {name}() 에 docstring 이 없습니다.")
    return out


def _contradicts(verdict: str, notes: str) -> bool:
    """pass 판정인데 notes 가 결함을 서술하는 모순인지 판별한다."""
    if verdict != "pass" or not notes:
        return False
    low = notes.lower()
    return any(w in low for w in _DEFECT_HINTS)

def _protected_files(explicit: str, criteria: str, files: list[str]) -> list[str]:
    """
    수정 금지 파일 목록을 만든다 (명시 인자 + AC 문장 자동 추출).

    측정 08 / S07: 모델이 수정 금지된 테스트를 재작성해 모순 요구를 "통과" 시켰다.
    AC 에 금지가 적혀 있어도 프롬프트만으로는 지켜지지 않으므로 결정론 가드가 필요하다.
    """
    out: list[str] = []
    for x in (explicit or "").split(","):
        x = x.strip()
        if x:
            out.append(x)
    markers = ("수정하지 말", "수정 금지", "변경하지 말", "do not modify",
               "do not change", "must not be modified", "unchanged")
    for line in criteria.splitlines():
        low = line.lower()
        if any(mk in line or mk in low for mk in markers):
            for rel in files:
                # 경계 매칭: 'test_x.py' 안의 'x.py' 처럼 부분 일치로 구현 파일까지
                # 보호되면 정상 수정이 막혀 오탐(치팅 판정)이 난다.
                if rel in out:
                    continue
                if re.search(r"(?<![\w./-])" + re.escape(rel) + r"(?![\w])", line):
                    out.append(rel)
    return out


def _snapshot(files: list[str]) -> dict[str, str]:
    """보호 파일의 현재 내용을 기록한다 (변경 감지용)."""
    snap: dict[str, str] = {}
    for rel in files:
        fp = _ROOT / rel
        if fp.is_file():
            snap[rel] = fp.read_text(encoding="utf-8", errors="replace")
    return snap


def _restore_violations(snap: dict[str, str]) -> list[str]:
    """
    보호 파일이 변경됐는지 확인하고, 변경된 파일은 원본으로 복원한다.

    복원은 ground truth 를 지키기 위한 것이며, 위반 사실은 숨기지 않고 반환해 상위에서
    fail 기록·에스컬레이션에 사용한다.
    """
    violated: list[str] = []
    for rel, original in snap.items():
        fp = _ROOT / rel
        current = fp.read_text(encoding="utf-8", errors="replace") if fp.is_file() else ""
        if current != original:
            violated.append(rel)
            fp.write_text(original, encoding="utf-8")
    return violated

def _artifact_problems(files: list[str]) -> list[str]:
    """
    산출 파일의 **형식 결함**을 결정론적으로 진단한다 (측정 08 라운드 10).

    로컬 모델이 write 도구로 파일을 만들 때 실제 개행 대신 리터럴 `\\n` 을 넣는 사례가
    실측됐다 (파일 전체가 한 줄 → 파이썬이 주석으로 처리 → 조용한 exit 0).
    모델에게 무엇이 잘못됐는지 알려주기 위해 사람이 읽을 수 있는 진단 문장을 반환한다.

    Returns:
        list[str]: 진단 문장 목록 (비었으면 형식 문제 없음)
    """
    problems: list[str] = []
    for rel in files:
        fp = _ROOT / rel
        if not fp.is_file():
            problems.append(f"{rel}: 파일이 없습니다.")
            continue
        body = fp.read_text(encoding="utf-8", errors="replace")
        real_lines = body.count("\n")
        literal = body.count("\\n")
        if literal and real_lines <= 1:
            problems.append(
                f"{rel}: 파일에 실제 줄바꿈이 없고 리터럴 두 글자 '\\n' 이 {literal}개 들어 있습니다. "
                "파일 내용은 실제 줄바꿈으로 여러 줄이어야 합니다."
            )
        elif real_lines == 0 and len(body) > 80:
            problems.append(f"{rel}: 전체가 한 줄입니다 (줄바꿈 없음).")
        # 공허 테스트 탐지 (측정 08 / S04): 테스트 파일에 assert 가 없으면 아무것도 검증하지
        # 않으면서 통과한다 — 결정론 grader 를 무력화하는 가장 위험한 패턴.
        # 파이썬 문법 검사 (측정 08 / S05·S06): 이스케이프 유출·구문 오배치를 정확히 지적한다.
        if rel.endswith(".py"):
            try:
                compile(body, rel, "exec")
            except SyntaxError as exc:
                problems.append(
                    f"{rel}: 문법 오류 {exc.lineno}행 — {exc.msg}. 해당 행: "
                    f"{(exc.text or '').strip()[:80]!r}"
                )
            except ValueError as exc:
                problems.append(f"{rel}: 컴파일 불가 — {exc}")
        # 이스케이프 유출 탐지: 파일 내용에 \" 가 들어가면 JSON 이스케이프가 새어 나온 것이다.
        if '\\"' in body:
            problems.append(
                f"{rel}: 이스케이프된 큰따옴표 문자열 backslash-quote 가 파일에 들어 있습니다 — "
                "파일에는 이스케이프하지 않은 실제 따옴표를 쓰십시오."
            )
        base = rel.split("/")[-1]
        is_test = base.startswith("test_") or base.endswith("_test.py")
        if is_test and "assert" not in body and "assertEqual" not in body:
            problems.append(
                f"{rel}: 테스트에 assert 문이 하나도 없습니다 — 요구된 동작을 실제로 검증하도록 "
                "assert 를 넣으십시오 (호출 후 print 만 하는 테스트는 무효)."
            )
    return problems


def _ensure_files(files: list[str], criteria: str, feature: str) -> list[str]:
    """
    대상 파일이 실제로 생성될 때까지 **파일 1건씩** 생성 지시하고 존재를 검증한다.

    측정 08: 로컬 모델은 (a) 쓰기 성공을 환각으로 보고하고 (b) 상대명을 `/path/to/...` 로
    훼손하며 (c) 절대경로는 호스트 권한이 거부한다. 따라서 파일 단위로 쪼개 지시하고
    드라이버가 파일시스템으로 결과를 확인하는 것이 유일하게 신뢰 가능한 방식이다.

    Returns:
        list[str]: 끝까지 생성되지 않은 파일 목록 (비었으면 전부 존재)
    """
    for rel in files:
        for attempt in (1, 2):
            if (_ROOT / rel).is_file():
                break
            hint = "\n".join(ln for ln in criteria.splitlines() if rel.split("/")[-1] in ln) or criteria
            task = (
                f"Create ONE file named {rel} — nothing else.\n"
                f"Call the edit tool with filePath exactly \"{rel}\" "
                "(a bare relative name: no leading slash, no directory, no placeholder path) "
                "and the complete file content.\n"
                f"Content requirements:\n{hint}\n"
                "Write the content with REAL line breaks (never the two characters "
                "backslash+n). Do not describe the file; create it. Reply DONE."
            )
            _log(f"  ✎ 파일 생성 지시: {rel} (시도 {attempt}/2)")
            _agent_call("developer", task)
            if (_ROOT / rel).is_file():
                _log(f"  ✓ 확인: {rel} 생성됨")
                break
            _log(f"  ✗ 미확인: {rel} 아직 없음 (모델 보고와 무관하게 파일시스템 기준)")
    return [rel for rel in files if not (_ROOT / rel).is_file()]


def cmd_run(args) -> int:
    """SDLC 사이클 상태 기계: develop → grade(재시도) → review → qa → bookkeep."""
    feature = args.feature
    files = [f.strip() for f in args.files.split(",")] if args.files else []

    # 대상 feature 로드
    fl_path = _ROOT / "feature_list.json"
    fl = json.loads(fl_path.read_text(encoding="utf-8"))
    feats = fl["features"] if isinstance(fl, dict) else fl
    feat = next((f for f in feats if f.get("id") == feature), None)
    if feat is None:
        _log(f"❌ {feature} 가 feature_list.json 에 없음")
        return 1
    criteria = "\n".join(f"- {c}" for c in feat.get("acceptance_criteria", []))

    # verify-loop 개시 (이미 있으면 이어감)
    if not _vl_state(feature):
        _vl(["start", feature, "--rubric", "code-review"])
    _log(f"▶ {feature} {feat.get('title', '')} — 사이클 시작 (grader: `{args.test_cmd}`)")
    _preflight()
    protected = _protected_files(getattr(args, "protect", "") or "", criteria, files)
    prot_snap = _snapshot(protected)
    if prot_snap:
        _log(f"  🔒 수정 금지 파일 보호: {list(prot_snap)}")

    # ── GRADE-FIRST (멱등 재개) ────────────────────────────────
    # 결정론 게이트가 이미 통과하면 생성 모델을 호출하지 않는다 (측정 07 교훈:
    # 재개 시 무조건 구현부터 부르면 14B 가 멀쩡한 산출물을 다시 망가뜨린다).
    prior_pass = any(a.get("grader") == "test" and a.get("verdict") == "pass"
                     for a in _vl_state(feature).get("attempts", []))
    ok, _out = _grade(args.test_cmd, args.expect) if prior_pass else (False, "")
    if ok:
        _log("① grader 선통과 + 이전 통과 기록 있음 — 구현 단계 생략 (재개/멱등)")
    else:
        # ── DEVELOP ────────────────────────────────────────────
        dev_prompt = (
            f"Implement feature {feature}: {feat.get('title', '')}.\n"
            f"Acceptance criteria:\n{criteria}\n"
            "Create the files in the current directory with exact relative filenames "
            "(no leading slash, no directories). Reply DONE when all files exist."
        )
        _log("① developer(생성형) 구현 호출")
        rc, _ = _agent_call("developer", dev_prompt)
        if rc == 124:
            _log("❌ developer 호출 실패 (호스트 연속 실패) — 중단")
            return 1
        # 환각 보고 방지: 파일 존재를 드라이버가 직접 확인하고, 없으면 파일별로 재지시
        missing = _ensure_files(files, criteria, feature)
        if missing:
            _log(f"❌ 대상 파일 생성 실패: {missing} — 상위 호스트 인계 (exit 2)")
            _vl(["record", feature, "--grader", "test", "--verdict", "fail",
                 "--notes", f"파일 생성 실패(환각 보고 가능): {missing}"])
            return 2

    # ── GRADE + REVISE 루프 (verify-loop 가 유계·에스컬레이션 관리) ──
    while True:
        violated = _restore_violations(prot_snap)
        if violated:
            _log(f"🚫 수정 금지 파일이 변경됨 (복원 완료): {violated} — 치팅으로 판정, 인계")
            _vl(["record", feature, "--grader", "test", "--verdict", "fail",
                 "--notes", f"수정 금지 파일 변경(테스트 약화 시도): {violated}"])
            return 2
        ok, out = _grade(args.test_cmd, args.expect)
        # 공허 통과 차단: 테스트가 통과해도 산출물 자체가 무효(assert 없음/한 줄 파일)면 실패로 본다.
        blocking = _artifact_problems(files) if ok else []
        if ok and blocking:
            _log("② grader 통과했으나 산출물 무효 — 실패 처리: " + blocking[0][:80])
            ok = False
            out = (out + "\n[driver] " + " / ".join(blocking))[-800:]
        if ok:
            _vl(["record", feature, "--grader", "test", "--verdict", "pass",
                 "--notes", "결정론 grader 통과 (exit 0 + 기대 출력 + 산출물 유효)"])
            _log("② grader PASS")
            break
        _vl(["record", feature, "--grader", "test", "--verdict", "revision",
             "--notes", f"grader 실패: {out[:120]}"])
        state = _vl_state(feature)
        revisions = sum(1 for a in state.get("attempts", []) if a.get("verdict") == "revision")
        _log(f"② grader FAIL (revision {revisions}) — 출력: {out[:100]}")
        if state.get("escalated") or revisions >= args.max_revisions:
            _log(f"🚨 에스컬레이션 — 상위 호스트(사람/Claude Code) 인계 필요. "
                 f"상태: python3 .claude/bin/verify_loop.py status {feature}")
            return 2
        # 재작업 = 전체 파일 재작성 (규칙 6) — 실패 출력 + 현재 내용을 드라이버가 주입
        fmt = _artifact_problems(files)
        # 기대 출력(--expect)이 없으면 그 사실을 명시적으로 지적한다: 모델이 관용적 테스트
        # 프레임워크로 바꿔 기대 토큰을 출력하지 않는 사례가 반복됐다 (측정 08 라운드 11).
        if args.expect and args.expect not in out:
            fmt.append(
                f"테스트 명령이 기대 토큰 '{args.expect}' 를 출력하지 않았습니다 "
                f"(현재 출력 일부: {out[-160:]!r}). unittest 등 프레임워크로 바꾸지 말고, "
                f"요구된 대로 plain assert 후 정확히 '{args.expect}' 를 print 하십시오."
            )
        if fmt:
            _log("  ⓘ 산출물 결함 감지: " + " / ".join(x[:60] for x in fmt))
        revise_prompt = (
            f"The implementation of {feature} fails its test.\n"
            f"Test command: {args.test_cmd}\nTest output:\n{out}\n\n"
            + ("PROBLEMS DETECTED (fix these exactly):\n" + "\n".join(f"- {x}" for x in fmt) +
               "\nWrite the file with REAL line breaks — never the two characters backslash+n.\n\n"
               if fmt else "")
            + f"{_files_context(files)}\n\n"
            "Identify the buggy file and REWRITE that file COMPLETELY with corrected "
            "content (do not use partial edits). Use the exact relative filename. Reply DONE."
        )
        _log("  ↻ developer 재작업 (전체 파일 재작성 지시)")
        rc, _ = _agent_call("developer", revise_prompt)
        if rc == 124:
            _log("❌ developer 재작업 호출 실패 — 중단")
            return 1

    # ── REVIEW / QA (판정은 로컬 32B judge — bash-only, 기록 여부는 드라이버가 검증) ──
    for role, ask in (
        ("reviewer", "judge code quality, correctness and test coverage"),
        ("qa", "verify every acceptance criterion is met"),
    ):
        before_n = max((a.get("n", 0) for a in _vl_state(feature).get("attempts", [])), default=0)
        mech = _mechanical_findings(files)
        judge_prompt = (
            f"You must {ask} for feature {feature} using ONLY the bash tool "
            f"(never the read tool).\n"
            f"Step 1: run bash: cat {' '.join(files)}\n"
            f"Step 2: run bash: {args.test_cmd}\n"
            f"Acceptance criteria:\n{criteria}\n"
            + ("Already detected by deterministic checks (weigh these):\n"
               + "\n".join(f"- {x}" for x in mech) + "\n" if mech else "")
            + "VERDICT RULE: passing tests are not sufficient. If ANY acceptance criterion is "
              "unmet — including a missing docstring — record --verdict revision. Use pass only "
              "when every criterion is satisfied.\n"
            + f"Step 3: record your verdict via bash (notes must state a concrete finding):\n"
              f"python3 .claude/bin/verify_loop.py record {feature} --grader {role} "
              f"--verdict pass --notes '<your concrete finding>'\n"
              f"(replace pass with revision per the VERDICT RULE)\n"
              f"The bash tool needs both arguments: command and description.\n"
              f"Reply PASS or NEEDS REVISION with one sentence."
        )
        _log(f"③ {role}(judge, 32B) 판정 호출")
        verdict = None
        for attempt in (1, 2, 3):
            prompt = judge_prompt
            if attempt > 1:
                # 응답은 했지만 기록 명령을 실행하지 않은 경우: 빠뜨린 동작만 콕 집어 재요청한다
                # (판정 내용은 여전히 judge 의 몫 — 드라이버가 대신 기록하지 않는다).
                prompt = (
                    f"Your previous reply did not record a verdict for {feature}. "
                    "The judgement is only valid once it is recorded.\n"
                    "Run this bash command now (fill notes with your concrete finding, and use "
                    "--verdict revision instead of pass if you found a must-fix issue):\n"
                    f"python3 .claude/bin/verify_loop.py record {feature} --grader {role} "
                    f"--verdict pass --notes '<your concrete finding>'\n"
                    "Remember the bash tool needs both arguments: command and description.\n"
                    "Then reply with PASS or NEEDS REVISION."
                )
            rc, _out = _agent_call(role, prompt)
            verdict = _judge_recorded(feature, role, before_n)
            if verdict:
                break
            tail = "재시도" if attempt < 3 else "중단"
            if rc == 124:
                _log(f"  ⚠️ {role} 호출이 호스트 실패로 무산 — {tail}")
            else:
                _log(f"  ⚠️ {role} 응답했으나 판정 미기록 — {tail}")
        if not verdict:
            _log(f"❌ {role} 판정 확보 실패 — 상위 호스트 인계 (exit 2)")
            return 2
        _log(f"  {role} verdict: {verdict}")
        # 모순 판정 교정: pass 인데 notes 가 결함을 서술하면 1회 재요청 (측정 08 / S02·S03).
        rec = next((a for a in reversed(_vl_state(feature).get("attempts", []))
                    if a.get("grader") == role), {})
        if _contradicts(verdict, rec.get("notes") or ""):
            _log(f"  ⚠️ {role} 모순 판정 (pass + 결함 서술) — 재판정 요청")
            before2 = max((a.get("n", 0) for a in _vl_state(feature).get("attempts", [])), default=0)
            _agent_call(role, (
                f"Your recorded verdict for {feature} is inconsistent: you recorded pass but your "
                f"notes describe an unmet criterion ({(rec.get('notes') or '')[:160]}).\n"
                "Per the VERDICT RULE an unmet acceptance criterion requires revision.\n"
                "Record the corrected verdict now via bash:\n"
                f"python3 .claude/bin/verify_loop.py record {feature} --grader {role} "
                f"--verdict revision --notes '<the unmet criterion>'\n"
                "The bash tool needs both arguments: command and description."
            ))
            corrected = _judge_recorded(feature, role, before2)
            if corrected:
                _log(f"  ↺ {role} 재판정 기록: {corrected}")
                verdict = corrected
        # judge revision → developer 재작업 → 재채점 → 재판정 (유계 루프, 측정 08 라운드 12)
        jround = 0
        while verdict != "pass":
            state = _vl_state(feature)
            revisions = sum(1 for a in state.get("attempts", []) if a.get("verdict") == "revision")
            if state.get("escalated") or revisions >= args.max_revisions or jround >= 2:
                _log(f"🚨 {role} 판정 미해결 (revision {revisions}) — 상위 호스트 인계 (exit 2)")
                return 2
            jround += 1
            rec_notes = ""
            for a in reversed(state.get("attempts", [])):
                if a.get("grader") == role and a.get("verdict") == "revision":
                    rec_notes = a.get("notes") or ""
                    break
            mech2 = _mechanical_findings(files)
            _log(f"  ↻ {role} 지적사항으로 developer 재작업 (judge 라운드 {jround}/2)")
            fix_prompt = (
                f"The {role} rejected {feature} and requires changes.\n"
                f"{role} finding: {rec_notes}\n"
                + ("Deterministic checks also report:\n"
                   + "\n".join(f"- {x}" for x in mech2) + "\n" if mech2 else "")
                + f"{_files_context(files)}\n\n"
                "Fix exactly these points by REWRITING the affected file COMPLETELY with the "
                "corrected content (relative filename, real line breaks). Keep the tests passing. "
                "Reply DONE."
            )
            _agent_call("developer", fix_prompt)
            violated2 = _restore_violations(prot_snap)
            if violated2:
                _log(f"🚫 수정 금지 파일 변경 (복원): {violated2} — 인계")
                _vl(["record", feature, "--grader", "test", "--verdict", "fail",
                     "--notes", f"수정 금지 파일 변경: {violated2}"])
                return 2
            ok2, out2 = _grade(args.test_cmd, args.expect)
            blk2 = _artifact_problems(files)
            if not ok2 or blk2:
                _vl(["record", feature, "--grader", "test", "--verdict", "revision",
                     "--notes", f"judge 재작업 후 grader 실패: {(out2 or ' '.join(blk2))[:120]}"])
                _log("  ② 재작업 후 grader 실패 — 다음 라운드에서 재시도")
                continue
            _vl(["record", feature, "--grader", "test", "--verdict", "pass",
                 "--notes", "judge 재작업 후 grader 통과"])
            before3 = max((a.get("n", 0) for a in _vl_state(feature).get("attempts", [])), default=0)
            _agent_call(role, judge_prompt)
            again = _judge_recorded(feature, role, before3)
            if not again:
                _log(f"  ⚠️ {role} 재판정 미기록 — 인계 (exit 2)")
                return 2
            verdict = again
            _log(f"  {role} 재판정: {verdict}")

    # ── BOOKKEEP (supervisor 북키핑 — QA pass 근거로 상태 반영) ──
    feat["passes"] = True
    feat["status"] = "done"
    fl_path.write_text(json.dumps(fl, ensure_ascii=False, indent=2), encoding="utf-8")
    prog = _ROOT / "claude-progress.txt"
    with prog.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## cycle-driver | {feature} PASSED — dev(14B)+judge(32B) 로컬 무인 사이클, "
                 f"verify-loop {len(_vl_state(feature).get('attempts', []))}기록\n")
    if (_ROOT / ".git").exists():
        subprocess.run(["git", "add", "-A"], cwd=_ROOT, capture_output=True)
        subprocess.run(["git", "commit", "-m",
                        f"feat({feature}): 로컬 무인 사이클 완료 (cycle_driver — dev 14B + judge 32B)"],
                       cwd=_ROOT, capture_output=True)
    _log(f"✅ {feature} 완료 — passes:true, status:done, 커밋 기록")
    return 0


def cmd_self(args) -> int:
    """의존성 점검: opencode CLI / verify_loop / feature_list / 모델 설정."""
    print("[cycle-driver] ── self check ──")
    oc = shutil.which("opencode")
    print(f"  opencode CLI: {'PASS — ' + oc if oc else 'FAIL (미설치 — opencode-setup.sh 참조)'}")
    print(f"  verify_loop.py: {'PASS' if _VL.is_file() else 'FAIL'}")
    print(f"  feature_list.json: {'PASS' if (_ROOT / 'feature_list.json').is_file() else 'FAIL'}")
    ocj = _ROOT / "opencode.json"
    print(f"  opencode.json (역할별 모델): {'PASS' if ocj.is_file() else 'CONCERN (전역 설정만 사용)'}")
    missing = _preflight()
    print(f"  역할 모델 해석: {'PASS (전부 해석 가능)' if not missing else f'FAIL {missing}'}")
    return 0


def main() -> None:
    """CLI 엔트리포인트."""
    parser = argparse.ArgumentParser(description="로컬 결정론 supervisor — SDLC 사이클 드라이버 (localllm 전용)")
    sub = parser.add_subparsers(dest="command")
    p_run = sub.add_parser("run", help="feature 하나를 사이클로 실행")
    p_run.add_argument("feature", help="feature ID (예: F001)")
    p_run.add_argument("--test-cmd", required=True, help="결정론 grader 명령 (예: 'python3 test_x.py')")
    p_run.add_argument("--expect", default=None, help="grader 기대 출력 문자열 (공허 통과 차단)")
    p_run.add_argument("--files", default="", help="대상 파일 목록 (쉼표 구분 — 재작업 주입·judge cat 용)")
    p_run.add_argument("--max-revisions", type=int, default=3, help="에스컬레이션 임계 (기본 3)")
    p_run.add_argument("--protect", default="", metavar="FILES",
                       help="수정 금지 파일 (쉼표 구분). AC 문장에서도 자동 추출한다.")
    sub.add_parser("self", help="의존성 점검")
    args = parser.parse_args()
    if args.command == "run":
        sys.exit(cmd_run(args))
    cmd_self(args)


if __name__ == "__main__":
    main()
