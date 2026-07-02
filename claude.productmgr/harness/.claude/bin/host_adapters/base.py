"""
base.py — HostAdapter 추상 베이스 클래스 + 토큰 카탈로그

외부 의존성 없음. Python stdlib abc + re + pathlib만 사용.

토큰 형식: {{HOST.TOOL.<name>}}, {{HOST.CMD.<name>}}, {{HOST.ENV.<name>}}, {{HOST.NAME}}
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

# ---------------------------------------------------------------------------
# 토큰 카탈로그 상수
# ---------------------------------------------------------------------------

# 정규화된 도구 이름 목록 (호스트 독립적 canonical 이름)
CANONICAL_TOOLS: list[str] = [
    "bash",
    "read",
    "write",
    "edit",
    "multiedit",
    "glob",
    "grep",
]

# SKILL.md 템플릿 토큰 정규식
# 매치 그룹:
#   group(1): 카테고리 (TOOL | CMD | ENV | NAME)
#   group(2): 세부 키 (없을 수 있음, NAME 경우)
# CMD 키는 하이픈(-)을 포함할 수 있음 (예: {{HOST.CMD.start-session}})
TOKEN_RE = re.compile(r"\{\{HOST\.(TOOL|CMD|ENV|NAME)\.?([a-zA-Z_-]*)\}\}")

# 토큰 카탈로그 문서 (참조용)
TOKEN_CATALOG: dict[str, str] = {
    "{{HOST.TOOL.bash}}": "셸 도구명",
    "{{HOST.TOOL.read}}": "파일 읽기 도구명",
    "{{HOST.TOOL.write}}": "파일 쓰기 도구명",
    "{{HOST.TOOL.edit}}": "파일 편집 도구명",
    "{{HOST.TOOL.multiedit}}": "다중 편집 도구명",
    "{{HOST.TOOL.glob}}": "파일 검색 도구명",
    "{{HOST.TOOL.grep}}": "텍스트 검색 도구명",
    "{{HOST.CMD.<name>}}": "슬래시 커맨드 호출 표기",
    "{{HOST.ENV.project_dir}}": "프로젝트 루트 환경변수",
    "{{HOST.NAME}}": "호스트 이름",
}


# ---------------------------------------------------------------------------
# HostAdapter 추상 베이스
# ---------------------------------------------------------------------------

class HostAdapter(ABC):
    """
    호스트별로 달라지는 부분을 추상화한 어댑터 인터페이스.

    4개 카테고리를 담당한다:
      A. 도구명 매핑 (tool_name)
      B. 커맨드 호출 표기 (command_invocation)
      C. 환경 컨텍스트 (project_dir_env_var)
      D. SKILL.md 렌더링 (render_skill_md)

    모든 구현체는 예외를 삼키고 안전한 fallback을 반환해야 한다.
    어댑터 실패가 사용자 작업을 차단해서는 안 된다 (hook-failure-tolerance 원칙).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        호스트 식별자 문자열.

        Returns:
            str: "claude-code" | "openclaw" | "codex" 등
        """

    @property
    @abstractmethod
    def is_stub(self) -> bool:
        """
        미구현 stub 어댑터 여부.

        Returns:
            bool: True면 안내 메시지만 출력하는 미완성 어댑터
        """

    @abstractmethod
    def tool_name(self, canonical: str) -> str:
        """
        canonical 도구명을 호스트별 실제 도구명으로 변환한다.

        Args:
            canonical: CANONICAL_TOOLS 중 하나
                       ("bash" | "read" | "write" | "edit" | "multiedit" | "glob" | "grep")

        Returns:
            str: 호스트에서 사용하는 실제 도구명
        """

    @abstractmethod
    def command_invocation(self, name: str) -> str:
        """
        커맨드 이름을 호스트별 호출 표기로 변환한다.

        Args:
            name: 커맨드 이름 (예: "plan-full", "handoff")

        Returns:
            str: 호스트별 호출 표기 (예: "/project:plan-full" for claude-code)
        """

    @abstractmethod
    def project_dir_env_var(self) -> str:
        """
        프로젝트 루트를 담는 환경변수 이름을 반환한다.

        Returns:
            str: 환경변수 이름 (예: "CLAUDE_PROJECT_DIR" for claude-code)
        """

    @property
    def stub_info(self) -> str:
        """
        stub 어댑터 안내 메시지를 반환한다.

        실구현 어댑터는 이 메서드를 재정의할 필요가 없다 (기본값 빈 문자열 반환).
        stub 어댑터 (is_stub=True) 는 반드시 재정의하여 다음을 안내해야 한다:
          - stub 상태임을 명시
          - 실구현이 어느 phase에서 가능한지
          - claude-code 로 fallback 하는 방법

        Returns:
            str: 안내 메시지. 실구현 어댑터는 빈 문자열 ("").
        """
        return ""

    def render_skill_md(self, template_path: str | Path) -> str | None:
        """
        SKILL.md.template 파일을 읽어 호스트별 토큰을 치환해 반환한다.

        stub 어댑터는 이 메서드를 재정의해 None을 반환해야 한다
        (None = 변경하지 않음, 기존 SKILL.md 보존).

        Args:
            template_path: .template 파일의 경로

        Returns:
            str | None: 치환된 내용. None이면 렌더 건너뜀.
        """
        try:
            path = Path(template_path)
            if not path.exists():
                return None
            content = path.read_text(encoding="utf-8")
            return self._replace_tokens(content)
        except Exception:
            return None

    def _replace_tokens(self, content: str) -> str:
        """
        content에서 {{HOST.*}} 토큰을 호스트별 값으로 치환한다.

        Args:
            content: 원본 템플릿 문자열

        Returns:
            str: 토큰이 치환된 문자열
        """
        def replacer(m: re.Match) -> str:
            category = m.group(1)
            key = m.group(2).lower() if m.group(2) else ""
            try:
                if category == "TOOL":
                    return self.tool_name(key)
                elif category == "CMD":
                    return self.command_invocation(key)
                elif category == "ENV":
                    if key == "project_dir":
                        return f"${self.project_dir_env_var()}"
                    return m.group(0)  # 알 수 없는 ENV 토큰은 원본 보존
                elif category == "NAME":
                    return self.name
                else:
                    return m.group(0)
            except Exception:
                return m.group(0)  # 치환 실패 시 원본 토큰 보존

        return TOKEN_RE.sub(replacer, content)

    def adapter_info(self) -> dict:
        """
        어댑터 메타데이터를 딕셔너리로 반환한다.

        Returns:
            dict: name, is_stub, tool_mapping, command_example, env_var 포함
        """
        tool_mapping = {}
        for t in CANONICAL_TOOLS:
            try:
                tool_mapping[t] = self.tool_name(t)
            except Exception:
                tool_mapping[t] = f"[오류: {t}]"

        return {
            "name": self.name,
            "is_stub": self.is_stub,
            "tool_mapping": tool_mapping,
            "command_example": {
                "handoff": self.command_invocation("handoff"),
                "plan-full": self.command_invocation("plan-full"),
            },
            "project_dir_env_var": self.project_dir_env_var(),
        }
