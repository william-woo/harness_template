# AGENTS.md — OpenCode 프로젝트 컨텍스트 (localllm 변형, d-2)

> 이 파일은 **OpenCode**(오픈소스 agent framework)가 읽는 프로젝트 컨텍스트입니다.
> Claude Code 의 `CLAUDE.md` 에 상당합니다. localllm 변형은 Claude Code 가 아니라
> **OpenCode + 로컬 LLM(Ollama)** 으로 하네스를 구동합니다 (F015 / ADR-009).
>
> 하네스의 전체 규칙·에이전트·커맨드는 `CLAUDE.md` 와 `.claude/` 를 그대로 따릅니다.
> 이 파일은 **OpenCode 호스트에서 달라지는 점 4가지**만 명시합니다.

## OpenCode 호스트 4대 차이 (Claude Code 대비)

OpenCode 의 에이전트 정의는 `.opencode/agent/*.md` 에 있습니다 — 이는 Claude Code 의
`.claude/agents/*.md` 를 `python3 .claude/bin/host.py render-agents` 로 변환한 산출물입니다.
도구·경로 사용 시 다음 4가지를 반드시 지키세요:

1. **상대경로 우선** — 로컬 모델은 `/home/...` 절대경로를 임의 생성하는 습관이 있습니다
   (PoC 측정 02). 파일 읽기·쓰기는 **프로젝트 루트 기준 상대경로**를 사용하세요.
   OpenCode 는 cwd 기반이므로 현재 작업 디렉토리가 곧 프로젝트 루트입니다.
   (Claude Code 의 `$CLAUDE_PROJECT_DIR` 상당 환경변수 없음 → `$PWD` 사용)

2. **파일 생성 = `edit`** — OpenCode 에는 `write` 도구가 없습니다. 신규 파일 생성도
   `edit` 도구로 합니다 (측정 02 에서 edit 의 신규파일 생성 PASS 확인).

3. **다중 편집 = `edit` 다회 호출** — OpenCode 에는 `multiedit` 도구가 없습니다.
   여러 곳을 고칠 때는 `edit` 를 여러 번 호출하세요 (한 번에 하나씩, 안전).

4. **하위 에이전트 = `task` 도구** — Claude Code 의 `Task` 도구는 OpenCode 에서 `task` 입니다.
   `task` 로 `.opencode/agent/<name>.md` 의 subagent(developer/reviewer/qa/...)를 spawn 합니다.
   단, **멀티스텝 값 전달은 14B 한계**(측정 03b) — 복잡한 오케스트레이션은 32B+ 권장
   (docs/poc/MODEL-GRADES.md 참조).

## 환경 설정

```bash
bash .claude/bin/opencode-setup.sh        # OpenCode 설치 + Ollama provider 설정
python3 .claude/bin/host.py render-agents # .claude/agents/ → .opencode/agent/ 변환
opencode agent list                       # 변환된 에이전트 인식 확인
```

## 모델 등급 (요약)

- **단일 역할** (developer/reviewer/qa 등): qwen2.5:14b 로 **즉시 가능**
- **이종 오케스트레이션** (orchestrate): 32B+ 권장 — 14B 는 멀티스텝 값 전달 실패

→ 상세: docs/poc/MODEL-GRADES.md, docs/poc/SUMMARY.md
