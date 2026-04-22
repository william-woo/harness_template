# Testing Skill

> E2E 테스트 및 인수 검증 스킬. **QA 롤**이 기능 완료 여부를 검증할 때 사용한다.
> `acceptance_criteria`를 기반으로 테스트 계획을 수립하고 실행한다.

## E2E 검증 전략

### API 기능 검증 (curl)

```bash
# 로그인 API 검증 예시
BASE_URL="http://localhost:3000"

# 정상 케이스
RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"pass123"}')

TOKEN=$(echo $RESPONSE | jq -r '.token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ FAIL: 로그인 토큰 발급 실패"
  echo "응답: $RESPONSE"
  exit 1
fi
echo "✅ PASS: 로그인 토큰 발급 성공"

# 잘못된 비밀번호
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"wrong"}')

if [ "$STATUS" != "401" ]; then
  echo "❌ FAIL: 잘못된 비밀번호에 401 반환 안 함 (실제: $STATUS)"
  exit 1
fi
echo "✅ PASS: 잘못된 비밀번호 거부"
```

### UI 기능 검증 (Playwright/Puppeteer MCP)

Codex CLI에서는 `~/.codex/config.toml`에 MCP 서버를 등록한 뒤 브라우저 자동화 툴을
Codex 세션에서 바로 호출할 수 있다.

```toml
# ~/.codex/config.toml
[mcp_servers.playwright]
command = "npx"
args    = ["-y", "@playwright/mcp@latest"]
enabled = true
```

Codex 세션에서는 자연어로 지시하면 등록된 MCP 툴을 선택해서 실행한다.

```
브라우저로 http://localhost:3000/login 열고,
#email 필드에 test@example.com, #password에 pass123 입력 후 로그인 버튼 클릭.
navigation 이후 URL에 /dashboard 포함 여부 확인해줘.
```

검증 결과 요약을 `tests/e2e/FXXX-*.test.md` 로 저장해서 회귀 기록으로 남긴다.

## 인수 기준 → 테스트 변환

```
acceptance_criteria의 각 항목을 독립된 테스트로 구현:

"로그인 성공 시 토큰을 반환한다"
  → test_login_success_returns_token()

"잘못된 비밀번호 입력 시 401 에러를 반환한다"
  → test_login_wrong_password_returns_401()

"토큰은 24시간 후 만료된다"
  → test_token_expires_after_24h()
```

## 회귀 테스트 저장

QA 완료된 기능의 검증 스크립트를 저장:
```
tests/e2e/
├── F001-setup.test.sh
├── F002-user-registration.test.ts
├── F003-login.test.ts
└── regression.sh      ← 모든 PASS 기능 smoke test
```

`regression.sh`는 매 세션 시작 시 실행 가능해야 함.
