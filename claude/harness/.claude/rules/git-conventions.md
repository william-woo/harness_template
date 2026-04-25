# Git 컨벤션

## 브랜치 전략

```
main          ← 배포 가능한 안정 코드 (직접 커밋 금지)
develop       ← 통합 브랜치 (선택적)
feature/F001-기능명    ← 기능 개발
fix/F003-버그설명      ← 버그 수정
chore/작업명           ← 설정, 의존성 등
```

## 커밋 메시지 규칙

```
<type>(<scope>): <제목>

[선택] 본문

[선택] 꼬리말
```

### Type 목록

| Type | 사용 시점 |
|---|---|
| `feat` | 새 기능 추가 |
| `fix` | 버그 수정 |
| `test` | 테스트 추가/수정 |
| `refactor` | 기능 변경 없는 코드 개선 |
| `docs` | 문서 작성/수정 |
| `chore` | 빌드, 설정, 의존성 관리 |
| `wip` | 미완성 중간 저장 (세션 인계용) |

### 커밋 예시

```bash
# ✅ 좋은 예시
git commit -m "feat(F001): 사용자 이메일/비밀번호 로그인 API 구현"
git commit -m "test(F001): 로그인 API 성공/실패 케이스 단위 테스트 추가"
git commit -m "fix(F003): 토큰 만료 시 자동 갱신 로직 누락 수정"
git commit -m "wip(F007): 결제 흐름 구현 중 - 카드 검증까지 완료"

# ❌ 나쁜 예시
git commit -m "fix"
git commit -m "수정"
git commit -m "Update files"
```

## PR/MR 규칙

PR 제목 형식: `[F001] 사용자 로그인 기능 구현`

PR 본문 템플릿:
```markdown
## 작업 내용
- Feature ID: F001
- 구현 내용: [설명]

## 변경 사항
- 추가: [파일명]
- 수정: [파일명]

## 테스트
- [ ] 단위 테스트 통과
- [ ] Reviewer 에이전트 리뷰 완료
- [ ] QA 에이전트 검증 완료

## 관련 이슈
- feature_list.json F001
```

## 커밋 빈도 가이드

에이전트는 다음 시점에 반드시 커밋:
1. 기능 구현 완료 시
2. 테스트 작성 완료 시
3. 리뷰 수정 완료 시
4. 세션 종료 전 (wip 커밋)
