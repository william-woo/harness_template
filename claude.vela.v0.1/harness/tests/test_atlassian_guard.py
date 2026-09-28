#!/usr/bin/env python3
"""Atlassian 쓰기 대상 제한을 잠근다 (철칙 — stdlib unittest).

왜 이 파일이 있는가:
  "허락한 Confluence 스페이스·Jira 프로젝트에만 쓴다" 는 사용자 철칙이다.
  `permissions.ask` 는 **호출마다 사람에게 묻지만 대상을 제한하지 않는다** —
  긴 자율 작업 끝의 승인 피로 한 번이면 엉뚱한 스페이스에 발행된다.

  그리고 MCP 도구 호출은 모델 → 커넥터로 **곧장** 간다. `atlassian_map.py` 는
  그 경로에 없으므로 파이썬 코드로는 아무것도 막지 못한다. **PreToolUse 훅만이
  실제 차단 지점**이고, 그래서 이 테스트는 훅을 직접 태운다.

  이 리포가 반복해서 배운 것: "막았다" 는 주장과 "실제로 막힌다" 는 다른 것이고,
  후자는 되돌려서 확인해야 한다 (`test_default_deny_가_실제로_막는다` 참조).

실행:
    python3 tests/test_atlassian_guard.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HARNESS = Path(__file__).resolve().parent.parent
_HOOK_REL = ".claude/hooks/pre-atlassian-write-check.sh"
_ALLOW_REL = ".claude/atlassian-targets.json"

W = "mcp__claude_ai_Atlassian_Rovo__"


class AtlassianWriteGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rel in (_HOOK_REL, _ALLOW_REL):
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_HARNESS / rel, dst)

    def tearDown(self):
        self.tmp.cleanup()

    def _allow(self, spaces=(), projects=()):
        p = self.root / _ALLOW_REL
        d = json.loads(p.read_text(encoding="utf-8"))
        d["confluence_spaces"] = list(spaces)
        d["jira_projects"] = list(projects)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def _call(self, tool: str, args: dict, raw: str | None = None) -> subprocess.CompletedProcess:
        payload = raw if raw is not None else json.dumps({"tool_name": W + tool,
                                                          "tool_input": args})
        return subprocess.run(
            ["bash", str(self.root / _HOOK_REL)], input=payload, capture_output=True,
            text=True, timeout=30, env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)})

    def assertBlocked(self, res, why=""):
        self.assertEqual(res.returncode, 2, f"통과했다 {why}: {res.stdout}{res.stderr}")

    def assertAllowed(self, res, why=""):
        self.assertEqual(res.returncode, 0, f"막혔다 {why}: {res.stdout}{res.stderr}")

    # ── 기본값은 전면 거부 (fail-closed) ──────────────────────────────────
    def test_허용_목록이_비면_모든_쓰기를_막는다(self):
        """저장소에 담겨 나가는 기본값이 곧 전면 거부여야 한다."""
        for tool, args in (("createConfluencePage", {"spaceKey": "SD", "title": "x"}),
                           ("addCommentToJiraIssue", {"issueIdOrKey": "PROJ-1"}),
                           ("createJiraIssue", {"projectKey": "PROJ"}),
                           ("transitionJiraIssue", {"issueIdOrKey": "PROJ-1"})):
            with self.subTest(tool=tool):
                self.assertBlocked(self._call(tool, args), f"({tool}, 빈 허용 목록)")

    def test_허용_목록_파일이_없으면_막는다(self):
        (self.root / _ALLOW_REL).unlink()
        self.assertBlocked(self._call("createConfluencePage", {"spaceKey": "SD"}))

    def test_허용_목록이_손상이면_막는다(self):
        for body in ("{ torn", "[]", "null", '{"confluence_spaces": "SD"}'):
            with self.subTest(body=body[:12]):
                (self.root / _ALLOW_REL).write_text(body, encoding="utf-8")
                self.assertBlocked(self._call("createConfluencePage", {"spaceKey": "SD"}))

    # ── 허용된 대상만 통과 ────────────────────────────────────────────────
    def test_허용된_대상만_통과한다(self):
        self._allow(spaces=["SD"], projects=["PROJ"])
        self.assertAllowed(self._call("createConfluencePage", {"spaceKey": "SD"}), "(SD)")
        self.assertAllowed(self._call("addCommentToJiraIssue", {"issueIdOrKey": "PROJ-42"}), "(PROJ-42)")
        self.assertBlocked(self._call("createConfluencePage", {"spaceKey": "IT"}), "(IT)")
        self.assertBlocked(self._call("editJiraIssue", {"issueIdOrKey": "OTHER-1"}), "(OTHER-1)")

    def test_대소문자가_달라도_같은_대상으로_본다(self):
        self._allow(spaces=["SD"], projects=["PROJ"])
        self.assertAllowed(self._call("createConfluencePage", {"spaceKey": "sd"}))
        self.assertAllowed(self._call("addCommentToJiraIssue", {"issueIdOrKey": "proj-7"}))

    # ── 우회 경로 ─────────────────────────────────────────────────────────
    def test_대상을_판별할_수_없으면_막는다(self):
        """숫자 id 만 주면 어느 스페이스인지 알 수 없다 — 확인 못 한 것은 통과시키지 않는다."""
        self._allow(spaces=["SD"], projects=["PROJ"])
        for args in ({"pageId": "12345"}, {"issueId": "10001"}, {}, {"title": "제목만"}):
            with self.subTest(args=str(args)[:30]):
                self.assertBlocked(self._call("updateConfluencePage", args))

    def test_URL_안의_대상도_검사한다(self):
        self._allow(spaces=["SD"], projects=["PROJ"])
        self.assertBlocked(self._call("createConfluenceFooterComment",
                                      {"url": "https://x.atlassian.net/wiki/spaces/IT/pages/1"}))
        self.assertBlocked(self._call("addCommentToJiraIssue",
                                      {"link": "https://x.atlassian.net/browse/OTHER-9"}))

    def test_허용과_비허용이_섞이면_막는다(self):
        """하나라도 허용 밖이면 거부한다 — 부분 통과는 없다."""
        self._allow(spaces=["SD"], projects=["PROJ"])
        self.assertBlocked(self._call("createConfluencePage",
                                      {"spaceKey": "SD", "parent": {"projectKey": "OTHER"}}))

    def test_중첩된_인자_안의_대상도_찾는다(self):
        self._allow(spaces=["SD"])
        self.assertBlocked(self._call("createConfluencePage",
                                      {"body": {"target": {"spaceKey": "IT"}}}))

    def test_훅_입력이_손상이면_막는다(self):
        self._allow(spaces=["SD"])
        for raw in ("not json", "", "[1,2]", '{"tool_input": "문자열"}'):
            with self.subTest(raw=raw[:12]):
                self.assertBlocked(self._call("x", {}, raw=raw))

    # ── 되돌림 검출 — 통과만으로는 증거가 아니다 ──────────────────────────
    def test_가드를_제거하면_테스트가_실패한다(self):
        """훅을 무력화(항상 exit 0)하면 위 케이스들이 통과해 버리는지 확인한다.

        이 테스트가 없으면 "막힌다" 는 주장의 근거가 훅 하나에만 있다.
        """
        hook = self.root / _HOOK_REL
        hook.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        self._allow(spaces=["SD"])
        res = self._call("createConfluencePage", {"spaceKey": "IT"})
        self.assertEqual(res.returncode, 0,
                         "무력화한 훅이 여전히 막는다 — 테스트가 훅을 태우지 않고 있다")


class SettingsWiringTest(unittest.TestCase):
    """훅이 **배선돼 있는가**. 스크립트만 있고 등록이 없으면 아무것도 막지 않는다."""

    def test_PreToolUse_에_Atlassian_matcher_가_있다(self):
        d = json.loads((_HARNESS / ".claude/settings.json").read_text(encoding="utf-8"))
        pre = d.get("hooks", {}).get("PreToolUse", [])
        hit = [m for m in pre if "atlassian" in json.dumps(m, ensure_ascii=False).lower()]
        self.assertTrue(hit, "PreToolUse 에 Atlassian 훅이 등록되지 않았다 — 선언만 있고 배선이 없다")
        matcher = hit[0].get("matcher", "")
        for verb in ("create", "update", "edit", "add", "transition", "delete"):
            self.assertIn(verb, matcher, f"matcher 가 '{verb}' 계열 도구를 덮지 않는다")

    def test_쓰기_도구가_전부_ask_에도_등재돼_있다(self):
        """훅은 대상을, `ask` 는 호출 자체를 막는다 — 두 층이 다 있어야 한다."""
        d = json.loads((_HARNESS / ".claude/settings.json").read_text(encoding="utf-8"))
        ask = set(d.get("permissions", {}).get("ask", []))
        for tool in ("createConfluencePage", "updateConfluencePage", "createJiraIssue",
                     "editJiraIssue", "addCommentToJiraIssue", "transitionJiraIssue"):
            self.assertIn(W + tool, ask, f"{tool} 이 permissions.ask 에 없다")

    def test_배포되는_허용_목록은_비어_있다(self):
        """이 변형을 가져가는 다운스트림이 남의 스페이스 키를 물려받으면 안 된다."""
        d = json.loads((_HARNESS / _ALLOW_REL).read_text(encoding="utf-8"))
        self.assertEqual(d.get("confluence_spaces"), [], "기본 허용 목록에 스페이스가 들어 있다")
        self.assertEqual(d.get("jira_projects"), [], "기본 허용 목록에 프로젝트가 들어 있다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
