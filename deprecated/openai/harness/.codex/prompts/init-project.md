# /init-project — 프로젝트 초기화 (Codex CLI)

새 프로젝트를 시작할 때 실행하는 초기화 슬래시 프롬프트.
**Planner 롤**로 전환해 요구사항을 분석하고 전체 환경을 셋업한다.

> 이 파일이 `~/.codex/prompts/init-project.md` 또는 프로젝트 `.codex/prompts/init-project.md`에 있으면 Codex CLI 세션에서 `/init-project` 로 호출된다.

---

당신은 지금부터 **Planner 롤** (`.codex/roles/planner.md`)로 동작합니다. 아래 7단계를 순서대로 자동으로 수행하세요.

## 실행 순서

1. **요구사항 수집** — 사용자에게 질문:
   - 프로젝트 목적이 무엇인가요?
   - 주요 기능 목록(우선순위 포함)을 알려주세요.
   - 기술 스택은 무엇인가요? (언어, 프레임워크, DB, 테스트 도구, 패키지 매니저)
   - 환경변수 목록은?
   - 헬스체크 URL은?

   **이미 모든 정보가 이번 턴에 주어졌다면 추가 질문 없이 바로 2단계로 진행**하세요.

2. **AGENTS.md 업데이트** — "프로젝트 개요"·"주요 명령어" 섹션을 실제 내용으로 채움 (편집 전 `bash .codex/scripts/pre-write-check.sh AGENTS.md` 호출)

3. **feature_list.json 생성** — 전체 기능 목록:
   - 모두 `passes: false`, `status: "todo"`
   - 각 기능에 `acceptance_criteria` 3개 이상
   - `dependencies` 명확히 설정
   - 작성 직후 `bash .codex/scripts/post-write-check.sh` 실행

4. **init.sh 작성** — 개발 서버 시작 및 기본 동작 확인 스크립트 (실제 기술 스택 명령어로)

5. **.env.example 생성** — 환경변수 목록 기반

6. **codex-progress.txt 초기화** — 세션 인계 파일에 초기 엔트리 append

7. **git 초기화 및 커밋**
   ```bash
   git init 2>/dev/null || true
   git add .
   git commit -m "chore: initialize project harness (Codex CLI)"
   ```

8. **첫 번째 작업 안내** — 최우선 기능을 Architect/Developer 롤에게 안내하고 `/role` 사용법 설명

## 생성되는 파일

```
project-root/
├── AGENTS.md                 ← 프로젝트 정보 채워짐
├── codex-progress.txt        ← 초기화됨
├── feature_list.json         ← 전체 기능 목록 생성됨
├── init.sh                   ← 환경 시작 스크립트
├── .env.example
└── docs/plan/
    └── requirements.md       ← 요구사항 문서
```

## 완료 출력 형식

```
✅ 프로젝트 초기화 완료
──────────────────────────────────
📋 생성된 Feature: N개
🎯 최우선 Feature: F001 - [제목]
👤 권장 다음 롤: [architect | developer]
   명령: /role [architect|developer]
──────────────────────────────────
```
