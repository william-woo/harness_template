# product-cycle 핸드오프 디렉토리

`/project:product-cycle` 실행 시 사이클별 산출물을 `<cycle-id>/` 하위에 단계별로 기록한다.
(00-brief → 01-plan → 02-design → 03-dev → 04-verify → 05-deploy)

- `<cycle-id>/` 런타임 산출물은 gitignore (ADR-008 핸드오프 규약 상속).
- `.gitkeep` + 이 README 는 커밋 대상 (디렉토리 보존 + 규약 설명).
