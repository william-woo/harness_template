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
7. **첫 번째 작업 안내** — 최우선 기능을 Architect/Developer에게 안내

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
