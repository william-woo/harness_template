"""
openclaw.py — OpenClaw 호스트 stub 어댑터

OpenClaw의 실제 스펙이 미확정이므로 안내 메시지만 반환하는 stub이다.
is_stub = True — 어댑터 미구현.

동작 원칙 (ADR-001 결정 4):
  - 차단하지 않고 안내만 출력한다
  - render_skill_md()는 None 반환 (= SKILL.md 수정 안 함)
  - 모든 메서드는 예외 없이 placeholder 문자열 반환
"""
from __future__ import annotations

from .base import HostAdapter

_STUB_NOTE = "[OpenClaw: 어댑터 미구현 — F006 후속 Feature 참조]"

_STUB_INFO = """\
[WARN] OpenClaw 어댑터는 현재 stub입니다 (F006 Phase 3).
  - 도구명 매핑, 커맨드 표기, 훅 모델은 후속 Feature에서 구현됩니다.
  - 현재는 claude-code 환경에서만 모든 기능이 정상 동작합니다.
  - claude-code 로 전환:
      HARNESS_AGENT_TYPE=claude-code
      또는 /project:host set claude-code
"""


class OpenClawAdapter(HostAdapter):
    """
    OpenClaw 호스트 stub 어댑터.

    OpenClaw의 도구명/커맨드/환경변수 스펙이 아직 미확정이다.
    모든 메서드는 placeholder 문자열을 반환하고 SKILL.md를 수정하지 않는다.
    """

    @property
    def name(self) -> str:
        """호스트 식별자를 반환한다."""
        return "openclaw"

    @property
    def is_stub(self) -> bool:
        """stub 어댑터이므로 True를 반환한다."""
        return True

    @property
    def stub_info(self) -> str:
        """stub 안내 메시지를 반환한다."""
        return _STUB_INFO

    def tool_name(self, canonical: str) -> str:
        """
        OpenClaw 도구명 (미구현 — placeholder 반환).

        Args:
            canonical: 정규화된 도구명

        Returns:
            str: placeholder 안내 문자열
        """
        return f"[OpenClaw.TOOL.{canonical}: 미구현 — 후속 Feature]"

    def command_invocation(self, name: str) -> str:
        """
        OpenClaw 커맨드 호출 표기 (미구현 — placeholder 반환).

        Args:
            name: 커맨드 이름

        Returns:
            str: placeholder 안내 문자열
        """
        return f"[OpenClaw.CMD.{name}: 미구현 — 후속 Feature]"

    def project_dir_env_var(self) -> str:
        """
        OpenClaw 프로젝트 루트 환경변수 (미구현 — placeholder 반환).

        Returns:
            str: placeholder 안내 문자열
        """
        return "OPENCLAW_WORKSPACE"  # 가설적 이름

    def render_skill_md(self, template_path) -> None:
        """
        stub 어댑터는 SKILL.md를 수정하지 않는다.

        Args:
            template_path: 무시됨

        Returns:
            None: 항상 None 반환 (= 변경 없음)
        """
        return None
