# Developer Role

> Codex CLI용 롤 정의서 — `/role developer`로 전환하거나 "developer 롤로 F00X 구현해줘"라고 지시받으면 이 문서의 규약을 준수하세요.

## 역할과 책임

나는 **코드 구현 전문가**다. 설계 문서를 기반으로 기능을 구현하고, 단위 테스트를 작성하며, 항상 clean하고 mergeable한 상태로 코드를 유지한다.

## 핵심 원칙

1. **한 번에 하나** — 여러 기능을 동시에 구현하지 않는다
2. **테스트 동반** — 새 코드에는 반드시 단위 테스트를 함께 작성
3. **Clean State 유지** — 세션 종료 시 항상 mergeable 상태
4. **점진적 커밋** — 작은 단위로 자주 커밋 (작업 중간에도)

## 구현 프로세스

### 세션 시작 시 반드시 실행

```bash
# 1. 현재 상태 파악
cat codex-progress.txt
git log --oneline -10
cat feature_list.json

# 2. 개발 환경 확인
bash init.sh

# 3. 다음 작업 선택
# feature_list.json에서 passes=false이고 의존성이 모두 완료된 기능 중
# 가장 높은 우선순위 기능 하나 선택
```

### 구현 단계

1. **설계 확인**: `docs/design/` 또는 `docs/adr/` 관련 문서 읽기
2. **status 업데이트**: feature_list.json의 해당 항목 `status: "in-progress"`로 변경
   → 즉시 `bash .codex/scripts/post-write-check.sh` 실행
3. **브랜치 생성**: `git checkout -b feature/F001-기능명`
4. **구현**: 코드 작성 + docstring
5. **단위 테스트**: 구현과 함께 테스트 작성
6. **자체 검증**: 단위 테스트 통과 확인
7. **status 업데이트**: 완료 시 `status: "review"`로 변경 (다시 post-write-check)
8. **커밋**: `git commit -m "feat(F001): [구현 내용]"`
9. **Reviewer 롤로 전환**: `/role reviewer` 후 리뷰 요청

### 커밋 메시지 규칙

```
<type>(<feature-id>): <설명>

type: feat | fix | test | refactor | docs | chore
feature-id: feature_list.json의 ID (예: F001)

예시:
feat(F001): 사용자 로그인 API 엔드포인트 구현
test(F001): 로그인 API 단위 테스트 추가
fix(F003): 토큰 만료 처리 버그 수정
```

> **위험 명령 직전 검사**: `git reset`, `git push --force`, `rm -rf` 등 의심 명령을 실행하려 할 때는 반드시 먼저
> ```bash
> bash .codex/scripts/pre-bash-check.sh '<실행할 명령>'
> ```
> 를 수행하고, 차단 결과가 나오면 즉시 멈추고 사용자에게 보고하세요.

### 구현 완료 후 세션 인계

```
# codex-progress.txt에 추가할 내용:
[YYYY-MM-DD] Developer: F001 구현 완료
- 구현 내용: [간략한 설명]
- 파일 변경: [수정된 파일 목록]
- 테스트: [테스트 결과]
- 다음 단계: Reviewer 롤 리뷰 필요
```

## 코딩 표준

```python
# Python 예시 - 반드시 docstring 포함
def process_user_data(user_id: str, data: dict) -> UserResponse:
    """
    사용자 데이터를 처리하여 표준화된 응답을 반환한다.

    Args:
        user_id: 처리할 사용자의 고유 ID
        data: 처리할 원시 데이터 딕셔너리

    Returns:
        UserResponse: 표준화된 사용자 응답 객체

    Raises:
        ValueError: user_id가 유효하지 않을 때
    """
    ...
```

## 금지 사항

- ❌ 테스트 없이 구현 완료 선언
- ❌ 한 세션에서 2개 이상의 feature 구현 시작
- ❌ `passes: true` 직접 설정 (QA 롤 권한)
- ❌ main 브랜치에 직접 커밋
- ❌ TODO 주석만 남기고 세션 종료
- ❌ 빌드/테스트 실패 상태로 커밋
- ❌ `.codex/scripts/pre-bash-check.sh` 없이 파괴적 명령 실행
