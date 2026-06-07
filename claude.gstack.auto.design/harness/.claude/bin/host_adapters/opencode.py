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

import re
from pathlib import Path

from .base import HostAdapter

# ---------------------------------------------------------------------------
# OpenCode 도구명 매핑 (ADR-009 결정 2)
# ---------------------------------------------------------------------------

# OpenCode 실측 도구 목록 (lowercase, ADR-009 결정 1):
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
    # 추가 Claude Code PascalCase 매핑 (agent frontmatter tools 파싱 시 정규화용)
    "webfetch": "webfetch",
    "task": "task",
    "todowrite": "todowrite",
    "websearch": "websearch",
}

# OpenCode 가 지원하는 전체 도구 집합 (ADR-009 결정 1, permission deny-list 생성에 사용)
_OPENCODE_ALL_TOOLS: frozenset[str] = frozenset({
    "bash", "read", "edit", "glob", "grep",
    "webfetch", "task", "todowrite", "websearch", "lsp", "skill",
})

# Claude Code PascalCase → lowercase 정규화 맵 (agent frontmatter tools: 필드 파싱용)
_CC_NORMALIZE: dict[str, str] = {
    "bash": "bash",
    "read": "read",
    "write": "edit",       # write → edit 융합
    "edit": "edit",
    "multiedit": "edit",   # multiedit → edit 융합
    "glob": "glob",
    "grep": "grep",
    "webfetch": "webfetch",
    "task": "task",
    "todowrite": "todowrite",
    "websearch": "websearch",
    "lsp": "lsp",
    "skill": "skill",
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

    # ---------------------------------------------------------------------------
    # agent 포맷 변환 (ADR-009 결정 1 — 정적 렌더링)
    # ---------------------------------------------------------------------------

    def render_agent_md(self, claude_agent_path: str | Path) -> str | None:
        """
        Claude Code agent 파일(.claude/agents/<name>.md)을 OpenCode 포맷으로 변환한다.

        ADR-009 결정 1: 정적 렌더링 (호출 시점 파일 생성).

        변환 규칙:
          - name: → 드롭 (파일명이 곧 agent name)
          - model: → 드롭 (OpenCode 는 frontmatter model: 미사용 — 호출 시점 --model 결정)
          - description: → 그대로
          - tools: A,B,C → permission deny-list 역변환
            (OpenCode 전체 도구 집합 - Claude 허용 도구 매핑 = denied 도구)
          - 본문 시스템 프롬프트: 그대로 ({{HOST.*}} 토큰 치환 적용)
          - mode: subagent (우리 7 에이전트 모두 subagent — ADR-009 결정 1)

        Args:
            claude_agent_path: .claude/agents/<name>.md 경로

        Returns:
            str | None: 변환된 OpenCode agent 내용. 실패 시 None.
        """
        try:
            path = Path(claude_agent_path)
            if not path.exists():
                return None
            content = path.read_text(encoding="utf-8")

            description, tools_raw, body = self._parse_claude_agent(content)
            permission = self._build_permission(tools_raw)
            body_rendered = self._replace_tokens(body)

            return self._format_opencode_agent(description, permission, body_rendered)
        except Exception:
            return None

    def _parse_claude_agent(self, content: str) -> tuple[str, list[str], str]:
        """
        Claude Code agent .md 파일에서 description, tools, body 를 추출한다.

        Args:
            content: 파일 전체 내용

        Returns:
            tuple[str, list[str], str]:
                description: frontmatter description 값 (멀티라인 포함)
                tools: Claude Code tools 목록 (쉼표 분리)
                body: frontmatter 아래 본문 텍스트
        """
        # frontmatter 파싱 (--- ... --- 블록)
        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
        if not fm_match:
            # frontmatter 없으면 전체를 body 로
            return "", [], content

        fm_text = fm_match.group(1)
        body = fm_match.group(2)

        description = self._extract_fm_field(fm_text, "description")
        tools_str = self._extract_fm_field(fm_text, "tools")
        tools = [t.strip() for t in tools_str.split(",") if t.strip()] if tools_str else []

        return description, tools, body

    def _extract_fm_field(self, fm_text: str, field: str) -> str:
        """
        frontmatter 텍스트에서 특정 필드 값을 추출한다.

        단순 값 (field: value) 과 블록 스칼라 (field: |\\n  ...) 모두 지원.

        Args:
            fm_text: frontmatter 텍스트 (--- 사이)
            field: 추출할 필드명

        Returns:
            str: 추출된 값 (없으면 빈 문자열). 멀티라인이면 공백 join.
        """
        lines = fm_text.split("\n")
        in_field = False
        field_lines: list[str] = []
        indent = 0

        for line in lines:
            if re.match(rf'^{re.escape(field)}\s*:', line):
                # 필드 시작
                rest = re.sub(rf'^{re.escape(field)}\s*:\s*', '', line).strip()
                if rest and rest not in ("|", ">", "|-", ">-"):
                    # 인라인 값 (단순 값)
                    return rest
                # 블록 스칼라 시작
                in_field = True
                indent = 0
                continue
            elif in_field:
                stripped = line.lstrip()
                if not line.strip():
                    field_lines.append("")
                    continue
                current_indent = len(line) - len(stripped)
                if indent == 0 and current_indent > 0:
                    indent = current_indent
                if current_indent >= indent:
                    field_lines.append(line[indent:] if indent > 0 else stripped)
                else:
                    # 들여쓰기 감소 → 다른 필드 시작
                    break

        return "\n".join(field_lines).strip()

    def _build_permission(self, claude_tools: list[str]) -> dict[str, str]:
        """
        Claude Code allow-list 를 OpenCode deny-list 로 역변환한다.

        ADR-009 결정 1 permission 역변환 알고리즘:
          opencode_all_tools - mapped_tools = denied_tools
          mapped_tools: claude_tools 를 _CC_NORMALIZE 로 정규화 (write→edit 등 융합 포함)

        Args:
            claude_tools: Claude Code frontmatter tools 목록 (예: ["Read", "Write", "Bash"])

        Returns:
            dict[str, str]: OpenCode permission dict (예: {"edit": "deny", "webfetch": "deny"})
                            빈 dict 이면 permission 생략 (전체 허용)
        """
        if not claude_tools:
            # tools 명시 없으면 permission 생략 (전체 허용)
            return {}

        # Claude 도구명 → OpenCode 도구명 정규화
        mapped: set[str] = set()
        for t in claude_tools:
            normalized = _CC_NORMALIZE.get(t.lower().strip(), t.lower().strip())
            mapped.add(normalized)

        # denied = 전체 도구 집합 - 허용된 도구
        denied = _OPENCODE_ALL_TOOLS - mapped

        return {tool: "deny" for tool in sorted(denied)}

    def _format_opencode_agent(
        self,
        description: str,
        permission: dict[str, str],
        body: str,
    ) -> str:
        """
        OpenCode agent .md 파일 내용을 생성한다.

        Args:
            description: 에이전트 설명 (description: 필드 값)
            permission: deny-list dict (비면 permission 필드 생략)
            body: 본문 시스템 프롬프트 (치환 완료)

        Returns:
            str: OpenCode 포맷 agent .md 전체 내용
        """
        lines = ["---"]

        # description 처리: 멀티라인이면 블록 스칼라 (>-) 사용
        if "\n" in description.strip():
            lines.append("description: >-")
            for dl in description.strip().split("\n"):
                lines.append(f"  {dl}")
        else:
            lines.append(f"description: {description.strip()}")

        lines.append("mode: subagent")

        if permission:
            lines.append("permission:")
            for tool, val in sorted(permission.items()):
                lines.append(f"  {tool}: {val}")

        lines.append("---")
        lines.append("")
        lines.append(body.rstrip())
        lines.append("")

        return "\n".join(lines)

    def render_agents(
        self,
        agents_src_dir: str | Path,
        agents_out_dir: str | Path,
    ) -> list[str]:
        """
        .claude/agents/*.md 를 OpenCode 포맷으로 변환하여 .opencode/agent/ 에 저장한다.

        ADR-009 결정 1: 정적 렌더링. 호출 시점에 파일 생성.
        기존 파일이 있으면 덮어쓴다 (멱등).

        Args:
            agents_src_dir: 소스 디렉토리 (.claude/agents/)
            agents_out_dir: 출력 디렉토리 (.opencode/agent/)

        Returns:
            list[str]: 생성된 파일명 목록 (예: ["developer.md", "planner.md", ...])
        """
        src = Path(agents_src_dir)
        out = Path(agents_out_dir)
        out.mkdir(parents=True, exist_ok=True)

        generated: list[str] = []
        for agent_file in sorted(src.glob("*.md")):
            result = self.render_agent_md(agent_file)
            if result is None:
                continue
            out_file = out / agent_file.name
            out_file.write_text(result, encoding="utf-8")
            generated.append(agent_file.name)

        return generated
