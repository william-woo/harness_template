# /project:init — 프로젝트 초기화

새 프로젝트를 시작할 때 실행하는 초기화 커맨드.
Planner 에이전트가 요구사항을 분석하고 전체 환경을 셋업한다.

## 실행 순서

1. **요구사항 수집** — 사용자에게 프로젝트 목적, 주요 기능, 기술 스택을 질문
2. **CLAUDE.md 업데이트** — 프로젝트 정보 섹션을 실제 내용으로 채움
3. **feature_list.json 생성** — 전체 기능 목록 (모두 `passes: false`, `status: "todo"`로 시작)
4. **init.sh 작성** — 개발 서버 시작 및 기본 동작 확인 스크립트
5. **claude-progress.txt 초기화** — 세션 인계 파일 생성
6. **git 초기화** — 초기 커밋 (`chore: initialize project harness`)
7. **OpenCode + 로컬 LLM 환경 설정 (localllm 변형 전용)** — `bash .claude/bin/opencode-setup.sh` 실행. OpenCode(전역 npm) 설치 + Ollama(로컬 LLM) provider 연결. ⚠️ autonomous #3-B: 전역 설치는 사용자 승인 필요. 미설치/거부 시 graceful degrade.
8. **첫 번째 작업 안내** — 최우선 기능을 Architect/Developer에게 안내

(선택) `/project:backup-sync init` 으로 백업 리포 설정 — 다른 머신·팀원과 산출물 동기화.

## localllm 변형 특이사항

이 변형은 **Claude Code 가 아니라 OpenCode + 로컬 LLM(Ollama)** 으로 하네스를 구동한다 (d-2 PoC).

```bash
bash .claude/bin/opencode-setup.sh        # OpenCode 설치 + Ollama provider 설정
# 환경변수로 서버·모델 override 가능:
OLLAMA_HOST=http://172.16.10.217:11434 OLLAMA_MODEL=qwen2.5:14b-instruct-q8_0 \
  bash .claude/bin/opencode-setup.sh
```

설정 후 하네스 활용:
```bash
opencode run --model ollama/qwen2.5:14b-instruct-q8_0 "<요청>"
# 또는 이 디렉토리를 OpenCode 프로젝트로 열기: opencode .
```

> 모델-무관 코어(brain/host/lint/backup/wiki/design_pick 헬퍼 + 훅 + git)는 로컬 LLM 에서도
> 100% 동작. 모델-의존(에이전트·스킬)은 로컬 모델 능력에 좌우 — PoC 측정은 docs/poc/ 참조.

## 실행

```
Use the planner agent to:
1. Ask me about project requirements, main features, and tech stack
2. Create feature_list.json with all features (passes: false, status: "todo")
3. Update CLAUDE.md project overview section
4. Write init.sh script
5. Initialize claude-progress.txt
6. Make initial git commit
7. Suggest the first feature to work on
```

## 생성되는 파일

```
project-root/
├── CLAUDE.md                 ← 프로젝트 정보 채워짐
├── claude-progress.txt       ← 초기화됨
├── feature_list.json         ← 전체 기능 목록 생성됨
├── init.sh                   ← 환경 시작 스크립트
└── docs/plan/
    └── requirements.md       ← 요구사항 문서
```
