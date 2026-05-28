---
name: testing
description: |
  E2E 테스트 및 인수 검증 스킬. QA 에이전트가 기능 완료 여부를 검증할 때 사용한다.
  acceptance_criteria를 기반으로 테스트 계획을 수립하고 실행한다.
---

# Testing Skill

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

### UI 기능 검증 (Puppeteer MCP)

```javascript
// Puppeteer MCP를 통한 브라우저 검증
// Claude Code에서 mcp__puppeteer__ 도구 사용

// 1. 브라우저 실행
await mcp.puppeteer.launch({ headless: true });

// 2. 로그인 플로우 검증
await mcp.puppeteer.navigate('http://localhost:3000/login');
await mcp.puppeteer.fill('#email', 'test@example.com');
await mcp.puppeteer.fill('#password', 'pass123');
await mcp.puppeteer.click('button[type="submit"]');
await mcp.puppeteer.waitForNavigation();

// 3. 결과 확인
const url = await mcp.puppeteer.getCurrentUrl();
if (!url.includes('/dashboard')) {
  throw new Error('로그인 후 대시보드로 이동하지 않음');
}
```

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
