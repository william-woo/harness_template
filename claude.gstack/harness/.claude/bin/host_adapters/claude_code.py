"""
claude_code.py — Claude Code 호스트 어댑터 (기본, 무회귀 보장)

현재 하네스가 사용하는 그대로의 Claude Code 도구명/커맨드/환경변수를 반환한다.
is_stub = False — 완전 구현 어댑터.
"""
from __future__ import annotations

from .base import HostAdapter


# ---------------------------------------------------------------------------
# Claude Code 도구명 매핑 테이블
# ---------------------------------------------------------------------------

_TOOL_MAP: dict[str, str] = {
    "bash": "Bash",
    "read": "Read",
    "write": "Write",
    "edit": "Edit",
    "multiedit": "MultiEdit",
    "glob": "Glob",
    "grep": "Grep",
}


class ClaudeCodeAdapter(HostAdapter):
    """
    Claude Code 호스트 어댑터.

    Claude Code 공식 도구명, /project:<name> 커맨드 표기,
    $CLAUDE_PROJECT_DIR 환경변수를 반환한다.

    기존 하네스 동작과 100% 동일 — 어떤 동작 변화도 없다.
    """

    @property
    def name(self) -> str:
        """호스트 식별자를 반환한다."""
        return "claude-code"

    @property
    def is_stub(self) -> bool:
        """완전 구현 어댑터이므로 False를 반환한다."""
        return False

    def tool_name(self, canonical: str) -> str:
        """
        canonical 도구명을 Claude Code 도구명으로 변환한다.

        Args:
            canonical: "bash" | "read" | "write" | "edit" | "multiedit" | "glob" | "grep"

        Returns:
            str: Claude Code 도구명 (예: "bash" → "Bash")

        Raises:
            KeyError: 알 수 없는 canonical 이름일 때 (호출자가 처리해야 함)
        """
        return _TOOL_MAP.get(canonical.lower(), canonical)

    def command_invocation(self, name: str) -> str:
        """
        커맨드 이름을 Claude Code 슬래시 커맨드 표기로 변환한다.

        Args:
            name: 커맨드 이름 (예: "plan-full", "handoff")

        Returns:
            str: Claude Code 슬래시 커맨드 (예: "/project:plan-full")
        """
        return f"/project:{name}"

    def project_dir_env_var(self) -> str:
        """
        Claude Code가 주입하는 프로젝트 루트 환경변수 이름을 반환한다.

        Returns:
            str: "CLAUDE_PROJECT_DIR"
        """
        return "CLAUDE_PROJECT_DIR"
