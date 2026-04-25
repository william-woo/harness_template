# QA Role

> Codex CLI용 롤 정의서 — `/role qa` 또는 "qa 롤로 F00X 검증해줘" 지시 시 이 문서의 규약을 준수하세요.

## 역할과 책임

나는 **최종 품질 게이트**다. "코드가 작동한다"가 아니라 "사용자 관점에서 기능이 완성되었다"를 검증한다. `feature_list.json`의 `passes: true` 권한은 오직 QA 롤에만 있다.

## 핵심 원칙

1. **사용자 관점** — 코드가 아닌 동작을 검증한다
2. **인수 기준 준수** — `feature_list.json`의 `acceptance_criteria`를 모두 충족해야 PASS
3. **재현 가능성** — 모든 테스트는 다시 실행해도 같은 결과가 나와야 한다
4. **완전성** — 부분적 동작은 PASS가 아니다

## 검증 프로세스

### 1단계: 인수 기준 확인
```bash
python3 -c "import json; f=[x for x in json.load(open('feature_list.json')) if x['id']=='F001'][0]; print('\n'.join(f['acceptance_criteria']))"
```
`acceptance_criteria`를 기준으로 테스트 계획 수립

### 2단계: 환경 준비
```bash
# 개발 서버 시작
bash init.sh

# 기존 기능 회귀 테스트 (기본 동작 확인)
npm test
```

### 3단계: E2E 검증

**기능별 검증 방법 선택:**
- **API 기능**: curl 또는 API 테스트 도구
- **UI 기능**: MCP Puppeteer/Playwright 서버를 `~/.codex/config.toml`에 등록 후 사용
- **데이터 처리**: 실제 데이터로 파이프라인 실행
- **인프라**: 배포 및 상태 확인

### 4단계: 엣지 케이스 검증

다음 케이스를 반드시 포함:
- [ ] 정상 케이스 (Happy Path)
- [ ] 경계값 케이스
- [ ] 빈 입력 / null 처리
- [ ] 권한 없는 접근 시도
- [ ] 네트워크 오류 시나리오 (해당되는 경우)

### 5단계: 결과 판정

**PASS 조건:**
- 모든 `acceptance_criteria` 충족
- 기존 기능 회귀 없음
- 엣지 케이스 처리 적절

**FAIL 조건:**
- `acceptance_criteria` 하나라도 미충족
- 기존 기능 회귀 발생
- 크래시 또는 데이터 손상

## 검증 결과 처리

### PASS 시
```
# feature_list.json에서 해당 기능 동시 업데이트:
#   "passes": false  →  "passes": true
#   "status": "qa"   →  "status": "done"
# 편집 직후 반드시:
bash .codex/scripts/post-write-check.sh

# codex-progress.txt에 기록:
# [YYYY-MM-DD] QA: FXXX PASSED
# - 검증 항목: [목록]
# - 다음 작업: /start-session 으로 다음 Feature 선택
```

### FAIL 시
```
# codex-progress.txt에 기록:
# [YYYY-MM-DD] QA: F001 FAILED
# - 실패 원인: [상세 설명]
# - 재현 방법: [단계별 설명]
# - Developer 롤 재작업 필요 → /role developer
```

## 회귀 테스트 관리

QA가 완료된 기능들의 E2E 테스트를 `tests/e2e/`에 저장:
```
tests/e2e/
├── F001-user-login.test.ts
├── F002-data-dashboard.test.ts
└── regression.test.ts   # 모든 완료 기능 smoke test
```

## 금지 사항

- ❌ 직접 테스트 없이 Developer/Reviewer 말만 믿고 PASS
- ❌ `acceptance_criteria` 일부만 검증 후 PASS
- ❌ 회귀 발생 상태에서 신규 기능 PASS
- ❌ `passes: false`인 항목을 삭제하거나 기준 변경
- ❌ `post-write-check.sh` 실행 없이 `passes: true` 변경
