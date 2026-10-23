# 하네스 템플릿 셋업 & 프로젝트 초기화 프롬프트 (Codex CLI 버전)

OpenAI Codex CLI에 그대로 붙여넣어 사용하는 프롬프트 모음입니다.
**STEP 1 → STEP 2 → STEP 3 순서대로** 실행합니다.

> 사전 준비:
> ```
> npm install -g @openai/codex     # 또는 brew install --cask codex
> codex                            # 또는 codex --profile work
> ```

---

## STEP 1. 하네스 템플릿 클론 및 분석

> 목적: GitHub에서 harness-template-codex를 클론하고, 구조와 역할을 파악한 뒤 현재 작업 디렉토리에 복사합니다.
> Codex CLI를 **프로젝트 작업 디렉토리에서** 실행한 상태에서 붙여넣으세요.

```
다음 작업을 순서대로 수행해줘.

## 1단계: 하네스 템플릿 클론

아래 저장소를 /tmp/harness-template에 클론해줘.

git clone https://github.com/<your-org>/harness-template-codex.git /tmp/harness-template

클론이 완료되면 전체 파일 목록을 출력해줘.

---

## 2단계: 템플릿 구조 분석

클론한 템플릿의 다음 파일들을 순서대로 읽고, 각 파일이 무엇을 하는지 한 줄씩 요약해줘.

읽어야 할 파일:
- /tmp/harness-template/AGENTS.md
- /tmp/harness-template/feature_list.json
- /tmp/harness-template/init.sh
- /tmp/harness-template/.codex/config.toml
- /tmp/harness-template/.codex/roles/planner.md
- /tmp/harness-template/.codex/roles/architect.md
- /tmp/harness-template/.codex/roles/developer.md
- /tmp/harness-template/.codex/roles/reviewer.md
- /tmp/harness-template/.codex/roles/qa.md
- /tmp/harness-template/.codex/prompts/init-project.md
- /tmp/harness-template/.codex/prompts/start-session.md
- /tmp/harness-template/.codex/prompts/handoff.md
- /tmp/harness-template/.codex/prompts/status.md
- /tmp/harness-template/.codex/prompts/role.md

분석이 끝나면 다음 형식으로 요약해줘.

### 템플릿 구조 요약
- 롤 N개: [목록]
- 슬래시 프롬프트 N개: [목록]
- 검증 스크립트 N개: [목록]
- 핵심 파일: [목록]

---

## 3단계: 현재 작업 디렉토리에 복사

현재 작업 디렉토리(pwd)를 확인하고, 아래 파일과 폴더를 복사해줘.
이미 존재하는 파일은 덮어쓰지 말고 목록만 알려줘.

복사 대상:
- /tmp/harness-template/.codex/              → ./.codex/
- /tmp/harness-template/AGENTS.md            → ./AGENTS.md
- /tmp/harness-template/feature_list.json    → ./feature_list.json
- /tmp/harness-template/codex-progress.txt   → ./codex-progress.txt
- /tmp/harness-template/init.sh              → ./init.sh
- /tmp/harness-template/.gitignore           → ./.gitignore
- /tmp/harness-template/docs/                → ./docs/

복사 후:
1. chmod +x .codex/scripts/*.sh init.sh 실행
2. (선택) cp -n .codex/prompts/*.md ~/.codex/prompts/ 로 전역 등록
3. 복사된 파일 목록 출력
4. 다음 단계(STEP 2)로 넘어갈 준비가 됐다고 알려줘
```

---

## STEP 2. 프로젝트 요구사항 전달 및 초기화

> 목적: Planner 롤에게 프로젝트 정보를 전달하고, 모든 초기화 파일을 자동 생성합니다.
> 아래 `[ ]` 부분을 실제 프로젝트 내용으로 채운 뒤 붙여넣으세요.

```
지금부터 planner 롤로 전환해서 아래 정보를 사용해 프로젝트를 초기화해줘.
추가 질문 없이 아래 스펙을 완전한 입력으로 간주하고
.codex/prompts/init-project.md의 8단계를 자동으로 수행해줘.

---

## 프로젝트 기본 정보

- 프로젝트명: [예: TaskFlow]
- 한 줄 설명: [예: 팀 단위 할일 관리 및 진행 현황 공유 웹 앱]
- 팀 규모: [예: 3명]
- 목표 완료일: [예: 2026-06-30]

---

## 기술 스택

- 언어: [예: TypeScript]
- 프레임워크: [예: Next.js 14 (App Router)]
- 데이터베이스: [예: PostgreSQL + Prisma ORM]
- 인증: [예: NextAuth.js]
- 스타일링: [예: Tailwind CSS]
- 테스트: [예: Vitest + Playwright]
- 배포: [예: Vercel]
- 패키지 매니저: [예: pnpm]

---

## 개발 환경 명령어

- 의존성 설치: [예: pnpm install]
- 개발 서버: [예: pnpm dev]
- 빌드: [예: pnpm build]
- 테스트: [예: pnpm test]
- 린트: [예: pnpm lint]
- 타입 체크: [예: pnpm typecheck]
- 헬스체크 URL: [예: http://localhost:3000/api/health]

---

## 환경변수 목록

[예:
- DATABASE_URL: PostgreSQL 연결 문자열
- NEXTAUTH_SECRET: NextAuth 시크릿 키
- NEXTAUTH_URL: 앱 배포 URL
- GOOGLE_CLIENT_ID: Google OAuth 클라이언트 ID
- GOOGLE_CLIENT_SECRET: Google OAuth 시크릿
]

---

## 주요 기능 목록

[기능을 우선순위 순서대로 작성하세요. "누가 무엇을 하면 어떻게 된다" 형식.]

[예:
1. 사용자가 Google 계정으로 로그인하면 대시보드로 이동한다 (critical)
2. 사용자가 태스크를 생성하면 목록에 추가된다 (critical)
3. 사용자가 태스크에 팀원을 할당하면 해당 팀원에게 알림이 간다 (high)
4. 팀원이 태스크 상태를 변경하면 실시간으로 반영된다 (high)
5. 관리자가 프로젝트를 생성하면 팀원을 초대할 수 있다 (medium)
6. 사용자가 완료된 태스크를 필터링하면 진행 통계를 볼 수 있다 (medium)
7. 사용자가 태스크에 댓글을 달면 팀원에게 알림이 간다 (low)
]

---

## 아키텍처 제약 조건

[예:
- API는 모두 /api/v1/ prefix 사용
- 모든 API 응답은 { data, error, meta } 구조
- DB 트랜잭션은 Prisma $transaction 사용
- 인증이 필요한 페이지는 middleware.ts에서 처리
- 컴포넌트는 Server Component 우선, 필요 시 "use client"
]

---

## 완료 기준

위 정보를 바탕으로 아래를 모두 수행해줘.

1. AGENTS.md의 프로젝트 개요, 기술 스택, 주요 명령어 섹션을 실제 내용으로 채워줘
2. feature_list.json을 위 기능 목록 기반으로 새로 생성해줘
   - 각 기능에 acceptance_criteria 3개 이상 포함
   - 의존성(dependencies) 명확히 설정
   - 모든 항목 passes: false, status: "todo" 로 시작
   - 작성 직후 bash .codex/scripts/post-write-check.sh 실행
3. init.sh를 위 기술 스택의 실제 명령어로 재작성해줘 (헬스체크 URL 포함)
4. .env.example 파일을 위 환경변수 목록으로 생성해줘
5. codex-progress.txt를 초기화 기록으로 업데이트해줘
6. git add -A && git commit -m "chore: initialize project harness (Codex CLI)" 실행해줘
7. 완료 후 첫 번째로 작업해야 할 Feature와 권장 /role 명령을 알려줘
```

---

## STEP 3. 초기화 결과 검증

> 목적: 초기화가 올바르게 완료됐는지 확인합니다.

```
초기화 결과를 검증해줘. 다음을 순서대로 확인해줘.

## 1. 파일 존재 확인

아래 파일이 모두 존재하는지 확인하고, 없으면 알려줘.

- AGENTS.md (프로젝트 정보가 채워졌는지 확인)
- feature_list.json (실제 기능 목록인지 확인)
- init.sh (실제 명령어로 작성됐는지 확인)
- .env.example
- codex-progress.txt
- .codex/config.toml
- .codex/roles/ (5개 롤 파일)
- .codex/scripts/ (4개 스크립트)
- .codex/prompts/ (5개 프롬프트)

## 2. 스크립트 실행 권한 확인

ls -la .codex/scripts/ 와 ls -la init.sh 로 실행 권한(x)이 있는지 확인해줘.
없으면 chmod +x 로 부여해줘.

## 3. feature_list.json 검증

feature_list.json을 읽고 다음을 확인해줘.
- 모든 항목에 passes: false
- 모든 항목에 status: "todo"
- 각 항목에 acceptance_criteria 3개 이상
- bash .codex/scripts/post-write-check.sh 실행 → exit 0 확인

## 4. 샌드박스·승인 정책 확인

.codex/config.toml 의 다음 값이 설정되었는지 확인:
- sandbox_mode = "workspace-write"
- approval_policy = "on-request"

## 5. 초기화 상태 출력

/status 를 실행하고 결과를 보여줘.

## 6. 최종 확인

모든 검증이 끝나면 아래 형식으로 결과를 알려줘.

### 초기화 완료 체크리스트
- [ ] 파일 구조 정상
- [ ] 스크립트 실행 권한 정상
- [ ] feature_list.json 형식 정상 (post-write-check PASS)
- [ ] 샌드박스 정책 설정됨
- [ ] git 커밋 완료
- [ ] 첫 번째 작업 Feature: [FXXX - 기능명]
- [ ] 권장 다음 명령: /role [architect|developer]

이제 /start-session 으로 개발을 시작할 수 있습니다.
```

---

## 참고: STEP 2 빠른 작성 가이드

STEP 2 프롬프트에서 채워야 할 `[ ]` 항목들입니다.

### 기술 스택 선택지 예시

| 항목 | 선택지 예시 |
|---|---|
| 언어 | TypeScript / Python / Go / Java |
| 웹 프레임워크 | Next.js / FastAPI / Express / Django / Spring Boot |
| 데이터베이스 | PostgreSQL / MySQL / MongoDB / SQLite |
| ORM | Prisma / SQLAlchemy / GORM / TypeORM |
| 인증 | NextAuth.js / JWT / OAuth2 / Supabase Auth |
| 테스트 | Vitest / Jest / pytest / Go test |
| 패키지 매니저 | pnpm / npm / pip / go mod |

### 기능 우선순위 기준

| 우선순위 | 기준 |
|---|---|
| critical | 이게 없으면 앱 자체가 동작 안 함 |
| high | 핵심 비즈니스 가치를 제공하는 기능 |
| medium | 사용성을 높이지만 없어도 동작은 함 |
| low | 나중에 추가해도 되는 부가 기능 |

### 기능 작성 형식

```
[사용자 유형]가 [행동]하면 [결과]가 된다 (우선순위)

예시:
- 비로그인 사용자가 회원가입 버튼을 누르면 가입 폼으로 이동한다 (critical)
- 관리자가 팀원을 초대하면 초대 이메일이 발송된다 (high)
- 사용자가 다크모드를 설정하면 다음 방문에도 유지된다 (low)
```

---

## 참고: 자주 쓰는 추가 프롬프트

### 새 기능 추가

```
/role planner

feature_list.json에 다음 새 기능을 추가해줘.

기능명: [기능명]
설명: [사용자]가 [행동]하면 [결과]가 된다
우선순위: [critical | high | medium | low]
의존성: [F001, F002 등, 없으면 빈 배열]
인수 기준:
- [검증 기준 1]
- [검증 기준 2]
- [검증 기준 3]

추가 후 반드시 bash .codex/scripts/post-write-check.sh 실행해줘.
```

### 특정 Feature 개발 시작

```
/start-session

이번 세션에서는 F003을 개발할 거야.
/role developer F003
```

### 현재 진행 상황 확인

```
/status
```

### 리뷰 세션 시작 (read-only)

```
/approvals on-request
/permissions              # 현재 정책 확인
/role reviewer F003
```

또는 아예 프로파일 전환:
```bash
# 현재 세션 종료 후
codex --profile review
```
