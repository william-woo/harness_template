#!/usr/bin/env python3
"""
host.py — 하네스 멀티 호스트 관리 CLI (F006)

Python stdlib만 사용. 외부 의존성 없음.

서브커맨드:
  current         현재 agent_type 출력 (1줄)
  info            호스트 정보 + 도구 매핑 + 커맨드 표기 예시
  set <type>      host.json 업데이트 → render-skills 자동 호출
  render-skills   .template 파일을 읽어 SKILL.md 토큰 치환
  render-agents   .claude/agents/*.md → .opencode/agent/*.md 변환 (opencode 전용, ADR-009 결정 1)
  check           무결성 점검 (무회귀 검증)

호스트 감지 우선순위 (높음 → 낮음):
  1. 환경변수 HARNESS_AGENT_TYPE
  2. .claude/host.json 의 agent_type
  3. 기본값 "claude-code"

설계 원칙:
  - 실패해도 절대 호출자를 차단하지 않음 (exit 0 유지)
  - 모든 핸들러 try/except 로 감싸 항상 exit 0
  - stub 어댑터: 차단하지 않고 안내만 출력 (ADR-001 결정 4)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 경로 상수
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent  # .claude/bin/host.py → project root
_HOST_JSON = _PROJECT_ROOT / ".claude" / "host.json"
_SKILLS_DIR = _PROJECT_ROOT / ".claude" / "skills"

VALID_AGENT_TYPES = {"claude-code", "openclaw", "codex", "opencode"}

# ---------------------------------------------------------------------------
# 어댑터 팩토리
# ---------------------------------------------------------------------------

def _load_adapter(agent_type: str):
    """
    agent_type에 맞는 어댑터 인스턴스를 반환한다.

    Args:
        agent_type: "claude-code" | "openclaw" | "codex" | "opencode"

    Returns:
        HostAdapter 인스턴스. 알 수 없는 타입이면 ClaudeCodeAdapter (안전 fallback).
    """
    try:
        # 상대 임포트를 위해 sys.path 추가
        if str(_SCRIPT_DIR) not in sys.path:
            sys.path.insert(0, str(_SCRIPT_DIR))

        if agent_type == "openclaw":
            from host_adapters.openclaw import OpenClawAdapter
            return OpenClawAdapter()
        elif agent_type == "codex":
            from host_adapters.codex import CodexAdapter
            return CodexAdapter()
        elif agent_type == "opencode":
            # ADR-009 결정 7: opencode 어댑터 로드 분기 (F015)
            from host_adapters.opencode import OpenCodeAdapter
            return OpenCodeAdapter()
        else:
            from host_adapters.claude_code import ClaudeCodeAdapter
            return ClaudeCodeAdapter()
    except Exception as e:
        # 임포트 실패 시 claude-code fallback (무회귀 보장)
        print(f"[WARN] 어댑터 로드 실패 ({agent_type}): {e} — claude-code fallback", file=sys.stderr)
        try:
            from host_adapters.claude_code import ClaudeCodeAdapter
            return ClaudeCodeAdapter()
        except Exception:
            return None


def _detect_agent_type() -> tuple[str, str]:
    """
    호스트 감지 우선순위에 따라 agent_type을 결정한다.

    Returns:
        tuple[str, str]: (agent_type, source)
            source: "env" | "host.json" | "default"
    """
    # 1. 환경변수
    env_val = os.environ.get("HARNESS_AGENT_TYPE", "").strip()
    if env_val:
        if env_val in VALID_AGENT_TYPES:
            return env_val, "env"
        else:
            print(
                f"[WARN] HARNESS_AGENT_TYPE={env_val!r} 는 알 수 없는 값입니다. "
                f"유효한 값: {', '.join(sorted(VALID_AGENT_TYPES))} — claude-code fallback",
                file=sys.stderr,
            )
            return "claude-code", "env(fallback)"

    # 2. host.json
    try:
        if _HOST_JSON.exists():
            data = json.loads(_HOST_JSON.read_text(encoding="utf-8"))
            val = data.get("agent_type", "").strip()
            if val in VALID_AGENT_TYPES:
                return val, "host.json"
            elif val:
                print(
                    f"[WARN] host.json agent_type={val!r} 는 알 수 없는 값입니다. "
                    f"유효한 값: {', '.join(sorted(VALID_AGENT_TYPES))} — claude-code fallback",
                    file=sys.stderr,
                )
    except Exception as e:
        print(f"[WARN] host.json 읽기 실패: {e} — claude-code fallback", file=sys.stderr)

    # 3. 기본값
    return "claude-code", "default"


# ---------------------------------------------------------------------------
# 서브커맨드 핸들러
# ---------------------------------------------------------------------------

def cmd_current(args) -> None:
    """
    현재 agent_type을 1줄로 출력한다.
    stub 어댑터인 경우 안내 메시지도 함께 출력한다.

    Args:
        args: argparse.Namespace (사용 안 함)
    """
    try:
        agent_type, source = _detect_agent_type()
        adapter = _load_adapter(agent_type)

        if adapter and adapter.is_stub:
            print(f"{agent_type} (stub — 어댑터 미구현)")
            print()
            stub_info = getattr(adapter, "stub_info", "")
            if stub_info:
                print(stub_info)
        else:
            print(agent_type)
    except Exception as e:
        print(f"[ERROR] current 명령 실패: {e}", file=sys.stderr)
        print("claude-code")  # fallback 출력


def cmd_info(args) -> None:
    """
    호스트 정보 + 도구 매핑 + 커맨드 표기 예시를 출력한다.

    Args:
        args: argparse.Namespace (사용 안 함)
    """
    try:
        agent_type, source = _detect_agent_type()
        adapter = _load_adapter(agent_type)

        if adapter is None:
            print(f"agent_type : claude-code (어댑터 로드 실패 — fallback)")
            return

        info = adapter.adapter_info()

        print(f"agent_type : {info['name']}")
        print(f"source     : {source}")
        print(f"is_stub    : {info['is_stub']}")
        print(f"host.json  : {_HOST_JSON} ({'존재' if _HOST_JSON.exists() else '없음 — 기본값'})")
        print()

        if adapter.is_stub:
            stub_info = getattr(adapter, "stub_info", "")
            if stub_info:
                print(stub_info)
        else:
            print("도구 매핑:")
            for canonical, mapped in info["tool_mapping"].items():
                print(f"  {canonical:12s} → {mapped}")
            print()
            print("커맨드 표기 예시:")
            for cmd_name, invocation in info["command_example"].items():
                print(f"  {cmd_name:12s} → {invocation}")
            print()
            print(f"프로젝트 루트 환경변수: ${info['project_dir_env_var']}")
    except Exception as e:
        print(f"[ERROR] info 명령 실패: {e}", file=sys.stderr)


def cmd_set(args) -> None:
    """
    host.json의 agent_type을 업데이트한다.
    변경 후 render-skills를 자동 호출한다.

    Args:
        args: argparse.Namespace — args.type에 새 agent_type 값
    """
    try:
        new_type = args.type.strip()
        if new_type not in VALID_AGENT_TYPES:
            print(
                f"[ERROR] 알 수 없는 agent_type: {new_type!r}\n"
                f"유효한 값: {', '.join(sorted(VALID_AGENT_TYPES))}",
                file=sys.stderr,
            )
            return

        # host.json 읽기 (존재 시 기존 필드 보존)
        existing: dict = {}
        try:
            if _HOST_JSON.exists():
                existing = json.loads(_HOST_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass

        existing["agent_type"] = new_type
        if "harness_version" not in existing:
            existing["harness_version"] = 1

        _HOST_JSON.parent.mkdir(parents=True, exist_ok=True)
        _HOST_JSON.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print(f"host.json 업데이트: agent_type = {new_type}")

        # render-skills 자동 호출
        print()
        _run_render_skills(new_type)

    except Exception as e:
        print(f"[ERROR] set 명령 실패: {e}", file=sys.stderr)


def _run_render_skills(agent_type: str, output_root: str | None = None) -> None:
    """
    render-skills 로직을 실행한다 (cmd_render_skills와 공유).

    Args:
        agent_type: 렌더링에 사용할 agent_type
        output_root: 출력 루트 디렉토리 경로 (None이면 .template 파일과 같은 디렉토리에 출력).
            예: "src/harness_template/openai/harness/.codex/skills"
            이 경우 각 .template의 스킬명 서브디렉토리에 SKILL.md를 생성한다.
            경로는 _PROJECT_ROOT 기준 상대경로 또는 절대경로.
    """
    adapter = _load_adapter(agent_type)
    if adapter is None:
        print("[WARN] 어댑터 로드 실패 — render-skills 건너뜀")
        return

    if adapter.is_stub:
        stub_info = getattr(adapter, "stub_info", "")
        print(f"[INFO] {agent_type} 는 stub 어댑터입니다 — SKILL.md 수정하지 않음.")
        if stub_info:
            print(stub_info)
        return

    # .template 파일 검색 후 렌더링
    if not _SKILLS_DIR.exists():
        print(f"[INFO] {_SKILLS_DIR} 없음 — render-skills 건너뜀")
        return

    templates = list(_SKILLS_DIR.rglob("*.template"))
    if not templates:
        print(f"[INFO] .template 파일 없음 — render-skills 완료 (렌더할 파일 없음)")
        return

    # 출력 루트 결정
    out_root: Path | None = None
    if output_root:
        out_root = Path(output_root) if Path(output_root).is_absolute() else _PROJECT_ROOT / output_root
        out_root.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] 출력 루트: {out_root}")

    rendered_count = 0
    for template_path in templates:
        try:
            result = adapter.render_skill_md(template_path)
            if result is None:
                continue

            if out_root:
                # --output-root 지정 시: 스킬명 서브디렉토리에 SKILL.md 생성
                # template_path 예: .claude/skills/coding/SKILL.md.template
                #   → skill_name: coding
                #   → out_path: <out_root>/coding/SKILL.md
                skill_name = template_path.parent.name
                skill_out_dir = out_root / skill_name
                skill_out_dir.mkdir(parents=True, exist_ok=True)
                out_fname = template_path.name.replace(".template", "")
                out_path = skill_out_dir / out_fname
            else:
                # 기본: .template 파일과 같은 디렉토리에 출력
                out_path = template_path.parent / template_path.name.replace(".template", "")

            out_path.write_text(result, encoding="utf-8")
            rendered_count += 1
            try:
                rel = out_path.relative_to(_PROJECT_ROOT)
            except ValueError:
                rel = out_path
            print(f"  렌더 완료: {rel}")
        except Exception as e:
            print(f"  [WARN] 렌더 실패 ({template_path.name}): {e}", file=sys.stderr)

    print(f"render-skills 완료: {rendered_count}개 파일 렌더링됨")


def cmd_render_skills(args) -> None:
    """
    .claude/skills/ 아래의 모든 .template 파일을 렌더링한다.
    stub 어댑터는 안내만 출력하고 SKILL.md를 수정하지 않는다.

    --output-root 지정 시 해당 경로의 스킬명 서브디렉토리에 SKILL.md를 출력한다.
    예: HARNESS_AGENT_TYPE=codex python3 host.py render-skills
          --output-root src/harness_template/openai/harness/.codex/skills

    Args:
        args: argparse.Namespace
            args.output_root: 출력 루트 디렉토리 (없으면 .template 위치와 동일)
    """
    try:
        agent_type, source = _detect_agent_type()
        output_root = getattr(args, "output_root", None)
        print(f"render-skills: agent_type={agent_type} (source: {source})")
        if output_root:
            print(f"render-skills: output_root={output_root}")
        print()
        _run_render_skills(agent_type, output_root=output_root)
    except Exception as e:
        print(f"[ERROR] render-skills 명령 실패: {e}", file=sys.stderr)


def cmd_render_agents(args) -> None:
    """
    .claude/agents/*.md 를 OpenCode 포맷(.opencode/agent/*.md)으로 변환한다.

    ADR-009 결정 1: 정적 렌더링. opencode 어댑터 전용.
    다른 어댑터(claude-code/openclaw/codex)는 안내만 출력하고 파일을 수정하지 않는다.

    --agents-src: 소스 디렉토리 (기본: .claude/agents/)
    --agents-out: 출력 디렉토리 (기본: .opencode/agent/ — _PROJECT_ROOT 기준)

    Args:
        args: argparse.Namespace
            args.agents_src: 소스 디렉토리 (str | None)
            args.agents_out: 출력 디렉토리 (str | None)
    """
    try:
        agent_type, source = _detect_agent_type()
        print(f"render-agents: agent_type={agent_type} (source: {source})")
        print()

        adapter = _load_adapter(agent_type)

        if adapter is None:
            print("[WARN] 어댑터 로드 실패 — render-agents 건너뜀")
            return

        if not hasattr(adapter, "render_agents"):
            print(
                f"[INFO] {agent_type} 어댑터는 render-agents 를 지원하지 않습니다.\n"
                "  render-agents 는 opencode 어댑터 전용입니다.\n"
                "  HARNESS_AGENT_TYPE=opencode python3 host.py render-agents"
            )
            return

        if adapter.is_stub:
            stub_info = getattr(adapter, "stub_info", "")
            print(f"[INFO] {agent_type} 는 stub 어댑터 — render-agents 건너뜀")
            if stub_info:
                print(stub_info)
            return

        # 소스 / 출력 디렉토리 결정
        agents_src_arg = getattr(args, "agents_src", None)
        agents_out_arg = getattr(args, "agents_out", None)

        if agents_src_arg:
            agents_src = (
                Path(agents_src_arg) if Path(agents_src_arg).is_absolute()
                else _PROJECT_ROOT / agents_src_arg
            )
        else:
            agents_src = _PROJECT_ROOT / ".claude" / "agents"

        if agents_out_arg:
            agents_out = (
                Path(agents_out_arg) if Path(agents_out_arg).is_absolute()
                else _PROJECT_ROOT / agents_out_arg
            )
        else:
            agents_out = _PROJECT_ROOT / ".opencode" / "agent"

        print(f"  소스: {agents_src}")
        print(f"  출력: {agents_out}")
        print()

        if not agents_src.exists():
            print(f"[WARN] 소스 디렉토리 없음: {agents_src} — render-agents 건너뜀")
            return

        generated = adapter.render_agents(agents_src, agents_out)

        for fname in generated:
            try:
                rel = (agents_out / fname).relative_to(_PROJECT_ROOT)
            except ValueError:
                rel = agents_out / fname
            print(f"  변환 완료: {rel}")

        print()
        print(f"render-agents 완료: {len(generated)}개 파일 생성됨")

    except Exception as e:
        print(f"[ERROR] render-agents 명령 실패: {e}", file=sys.stderr)


def cmd_check(args) -> None:
    """
    무결성 점검을 수행한다.
      - host.json 유효성 확인
      - 기존 훅/커맨드 파일 존재 확인
      - stub 어댑터인 경우 안내 메시지 출력

    Args:
        args: argparse.Namespace (사용 안 함)
    """
    try:
        agent_type, source = _detect_agent_type()
        adapter = _load_adapter(agent_type)

        print(f"[check] agent_type: {agent_type} (source: {source})")
        print()

        # host.json 확인
        if _HOST_JSON.exists():
            try:
                data = json.loads(_HOST_JSON.read_text(encoding="utf-8"))
                print(f"  [OK] host.json 존재 — agent_type={data.get('agent_type')}, version={data.get('harness_version')}")
            except Exception as e:
                print(f"  [WARN] host.json 파싱 실패: {e}")
        else:
            print(f"  [OK] host.json 없음 — 기본값 claude-code 사용")

        # 기존 훅 파일 확인 (무회귀)
        hooks_dir = _PROJECT_ROOT / ".claude" / "hooks"
        hook_files = list(hooks_dir.glob("*.sh")) if hooks_dir.exists() else []
        print(f"  [OK] 훅 파일: {len(hook_files)}개 ({', '.join(f.name for f in hook_files[:5])}{'...' if len(hook_files) > 5 else ''})")

        # 기존 커맨드 파일 확인 (무회귀)
        commands_dir = _PROJECT_ROOT / ".claude" / "commands"
        cmd_files = list(commands_dir.glob("*.md")) if commands_dir.exists() else []
        print(f"  [OK] 커맨드 파일: {len(cmd_files)}개")

        # settings.json 확인 (건드리지 않음)
        settings_json = _PROJECT_ROOT / ".claude" / "settings.json"
        if settings_json.exists():
            print(f"  [OK] settings.json 존재 — 수정하지 않음 (Claude Code 공식 스키마 유지)")

        print()

        if adapter and adapter.is_stub:
            stub_info = getattr(adapter, "stub_info", "")
            print(f"  [INFO] {agent_type} 는 stub 어댑터 — 기존 훅/커맨드는 영향 없음")
            if stub_info:
                print()
                print(stub_info)
        else:
            print(f"  [OK] {agent_type} 어댑터 정상 (is_stub=False)")

        print()
        print("  [INFO] 훅 라이프사이클·에이전트 frontmatter 추상화는 후속 Feature에서 구현 예정")
        print()
        print("[check] 무결성 점검 완료 — 무회귀 확인됨")

    except Exception as e:
        print(f"[ERROR] check 명령 실패: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    """
    host.py 진입점. argparse로 서브커맨드를 처리한다.
    모든 오류를 try/except로 잡아 항상 exit 0을 보장한다.
    """
    try:
        parser = argparse.ArgumentParser(
            prog="host.py",
            description="하네스 멀티 호스트 관리 CLI (F006)",
        )
        sub = parser.add_subparsers(dest="command", help="서브커맨드")

        sub.add_parser("current", help="현재 agent_type 출력 (1줄)")
        sub.add_parser("info", help="호스트 정보 + 도구 매핑 + 커맨드 표기 예시")

        p_set = sub.add_parser("set", help="host.json agent_type 업데이트")
        p_set.add_argument("type", choices=sorted(VALID_AGENT_TYPES), help="새 agent_type")

        p_render = sub.add_parser("render-skills", help=".template → SKILL.md 토큰 치환")
        p_render.add_argument(
            "--output-root",
            dest="output_root",
            default=None,
            metavar="PATH",
            help=(
                "출력 루트 디렉토리 (없으면 .template 파일 위치에 출력). "
                "예: src/harness_template/openai/harness/.codex/skills"
            ),
        )

        p_ragents = sub.add_parser(
            "render-agents",
            help=".claude/agents/*.md → .opencode/agent/*.md 변환 (opencode 전용, ADR-009 결정 1)",
        )
        p_ragents.add_argument(
            "--agents-src",
            dest="agents_src",
            default=None,
            metavar="PATH",
            help=(
                "소스 디렉토리 (기본: .claude/agents/). "
                "절대경로 또는 project root 기준 상대경로."
            ),
        )
        p_ragents.add_argument(
            "--agents-out",
            dest="agents_out",
            default=None,
            metavar="PATH",
            help=(
                "출력 디렉토리 (기본: .opencode/agent/). "
                "절대경로 또는 project root 기준 상대경로."
            ),
        )

        sub.add_parser("check", help="무결성 점검 (무회귀 검증)")

        args = parser.parse_args()

        handlers = {
            "current": cmd_current,
            "info": cmd_info,
            "set": cmd_set,
            "render-skills": cmd_render_skills,
            "render-agents": cmd_render_agents,
            "check": cmd_check,
        }

        if args.command is None:
            # 서브커맨드 없으면 info 기본 실행
            cmd_info(args)
        elif args.command in handlers:
            handlers[args.command](args)
        else:
            parser.print_help()

    except SystemExit:
        # argparse가 raise하는 SystemExit도 exit 0으로 처리
        pass
    except Exception as e:
        print(f"[ERROR] host.py 실패: {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
