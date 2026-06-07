"""
opencode.py — OpenCode 호스트 어댑터 (d-2 로컬 LLM 실구현)

OpenCode (오픈소스 agent framework) 도구명/커맨드/포맷을 반환한다.
is_stub = False — 실동작 어댑터 (F015).

OpenCode 실측 (ADR-009, opencode 1.16.2):
  - 도구: bash/read/edit/glob/grep/... (lowercase)
    write/multiedit 없음 → edit 로 융합 (측정 02: edit 가 신규파일+다회편집 겸용 PASS)
  - agent: <dir>/agents/<name>.md
    frontmatter: description + mode: all|primary|subagent
                 + permission: {<tool>: allow|ask|deny} (deny-list)
  - command: opencode run --command <name>
  - 프로젝트 env var: OpenCode 는 cwd 기반 — CLAUDE_PROJECT_DIR 상당 없음
                      (ADR-009: "관찰 안 됨" — placeholder 유지, PWD 사용 권고)
"""
from __future__ import annotations

from .base import HostAdapter

# ---------------------------------------------------------------------------
# OpenCode 도구명 매핑 (ADR-009 결정 2)
# ---------------------------------------------------------------------------

# OpenCode 실측 도구 목록 (lowercase):
#   bash, read, edit, glob, grep, webfetch, task, todowrite, websearch, lsp, skill
#
# Claude Code 대비 차이:
#   write 없음  → edit 가 신규 파일 생성 겸용 (측정 02 PASS 근거)
#   multiedit 없음 → edit 를 여러 번 호출하는 패턴으로 대체 (스킬 보강으로 안내, 결정 5)
_TOOL_MAP: dict[str, str] = {
    "bash": "bash",
    "read": "read",
    "write": "edit",       # OpenCode 에 write 없음 → edit 가 신규 파일 생성 겸용
    "edit": "edit",
    "multiedit": "edit",   # OpenCode 에 multiedit 없음 → edit 다회 호출로 대체
    "glob": "glob",
    "grep": "grep",
}


class OpenCodeAdapter(HostAdapter):
    """
    OpenCode 호스트 어댑터 (d-2 로컬 LLM 실구현).

    F015 Phase 11 산출물. ADR-009 결정 2·3·7 구현.

    OpenCode(오픈소스 AI agent framework)의 도구명/커맨드/환경변수를 반환한다.
    Claude Code 의 PascalCase 도구명, /project: 커맨드 표기와 달리
    OpenCode 는 lowercase 도구명, opencode run --command 표기를 사용한다.

    is_stub = False — 실측(5회 PoC) 기반 실구현. codex/openclaw stub 과 달리
    모든 메서드가 실제 OpenCode 동작에 대응하는 값을 반환한다.
    """

    @property
    def name(self) -> str:
        """호스트 식별자를 반환한다."""
        return "opencode"

    @property
    def is_stub(self) -> bool:
        """완전 구현 어댑터이므로 False를 반환한다."""
        return False

    def tool_name(self, canonical: str) -> str:
        """
        canonical 도구명을 OpenCode 도구명으로 변환한다.

        ADR-009 결정 2: write/multiedit → edit 융합.
        OpenCode 에 write/multiedit 가 없으므로 edit 로 매핑한다.
        측정 02 가 OpenCode edit 로 신규 파일 생성 PASS 를 확인 — 융합은 안전.

        Args:
            canonical: CANONICAL_TOOLS 중 하나
                       ("bash" | "read" | "write" | "edit" | "multiedit" | "glob" | "grep")

        Returns:
            str: OpenCode 도구명 (예: "bash" → "bash", "write" → "edit")
        """
        return _TOOL_MAP.get(canonical.lower(), canonical.lower())

    def command_invocation(self, name: str) -> str:
        """
        커맨드 이름을 OpenCode 커맨드 호출 표기로 변환한다.

        ADR-009 결정 3: opencode run --command <name> 표기 채택.
        - CLI headless 호환 (`opencode run --help` 실측 확인)
        - community 패턴: .opencode/command/<name>.md 파일 생성 시 호출 가능
        - 실제 .opencode/command/*.md 미러링은 F016 (후속 phase) 에서 수행

        Args:
            name: 커맨드 이름 (예: "plan-full", "handoff", "design-review")

        Returns:
            str: OpenCode 커맨드 호출 표기 (예: "opencode run --command plan-full")
        """
        # ADR-009 결정 3: opencode run --command 표기 (커맨드 파일 미러링은 F016)
        return f"opencode run --command {name}"

    def project_dir_env_var(self) -> str:
        """
        프로젝트 루트를 담는 환경변수 이름을 반환한다.

        ADR-009 실측: OpenCode 는 cwd 기반으로 동작하며,
        Claude Code 의 $CLAUDE_PROJECT_DIR 에 상당하는 환경변수가 관찰되지 않음.
        실제 프로젝트 루트가 필요한 경우 $PWD 또는 cwd() 를 사용하도록
        스킬/AGENTS.md 에서 안내한다.

        현재 placeholder "PWD" 를 반환 — base.py 토큰 치환에서
        $PWD 로 표기되어 shell 표준 변수를 가리킨다.

        Returns:
            str: "PWD" (shell 표준 현재 디렉토리 변수 — OpenCode cwd 기반 동작과 일치)
        """
        return "PWD"
