"""
codex.py — Codex 호스트 stub 어댑터

OpenAI Codex CLI의 실제 스펙이 미확정이므로 안내 메시지만 반환하는 stub이다.
is_stub = True — 어댑터 미구현.

동작 원칙 (ADR-001 결정 4):
  - 차단하지 않고 안내만 출력한다
  - render_skill_md()는 None 반환 (= SKILL.md 수정 안 함)
  - 모든 메서드는 예외 없이 placeholder 문자열 반환

참고:
  - src/harness_template/openai/harness/.codex/skills/coding/SKILL.md 는
    세션 2에서 수동 생성된 정적 산출물입니다. 직접 수정 금지.
  - codex 어댑터가 실구현되는 후속 phase에서 render_skill_md() 를 통한
    openai/ 변형 자동 재생성이 가능해집니다 (현재는 수동 산출물로 보존).
"""
from __future__ import annotations

from .base import HostAdapter

_STUB_NOTE = "[Codex: 어댑터 미구현 — F006 후속 Feature 참조]"

_STUB_INFO = """\
[WARN] Codex 어댑터는 현재 stub입니다 (F006 Phase 3).
  - 도구명 매핑, 커맨드 표기, 훅 모델은 후속 Feature에서 구현됩니다.
  - 현재는 claude-code 환경에서만 모든 기능이 정상 동작합니다.
  - render-skills 실행 시 .claude/skills/SKILL.md 는 변경되지 않습니다 (의도된 무회귀).
  - openai/ 변형 자동 재생성은 codex 어댑터가 실구현되는 후속 phase에서 가능합니다.
  - claude-code 로 전환:
      HARNESS_AGENT_TYPE=claude-code
      또는 /project:host set claude-code
"""


class CodexAdapter(HostAdapter):
    """
    Codex 호스트 stub 어댑터.

    OpenAI Codex CLI의 도구명/커맨드/환경변수 스펙이 아직 미확정이다.
    모든 메서드는 placeholder 문자열을 반환하고 SKILL.md를 수정하지 않는다.
    """

    @property
    def name(self) -> str:
        """호스트 식별자를 반환한다."""
        return "codex"

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
        Codex 도구명 (미구현 — placeholder 반환).

        Args:
            canonical: 정규화된 도구명

        Returns:
            str: placeholder 안내 문자열
        """
        return f"[Codex.TOOL.{canonical}: 미구현 — 후속 Feature]"

    def command_invocation(self, name: str) -> str:
        """
        Codex 커맨드 호출 표기 (미구현 — placeholder 반환).

        Args:
            name: 커맨드 이름

        Returns:
            str: placeholder 안내 문자열
        """
        return f"[Codex.CMD.{name}: 미구현 — 후속 Feature]"

    def project_dir_env_var(self) -> str:
        """
        Codex 프로젝트 루트 환경변수 (미구현 — placeholder 반환).

        Returns:
            str: placeholder 안내 문자열 (가설적 이름)
        """
        return "CODEX_PROJECT_ROOT"  # 가설적 이름 — 실제 스펙 확정 시 갱신

    def render_skill_md(self, template_path) -> None:
        """
        stub 어댑터는 SKILL.md를 수정하지 않는다.

        Args:
            template_path: 무시됨

        Returns:
            None: 항상 None 반환 (= 변경 없음)
        """
        return None
