# consortium 상태 디렉토리 (claude.productnw, d-3)

`consortium.py` 의 런타임 상태:
- `roster.json` — 등록된 팀·에이전트 (init 생성)
- `inbox/` — 수신 메시지 (게이트웨이가 외부→여기로 적재)
- `outbox/` — 송신 대기 메시지 (send 가 기록, 게이트웨이가 외부로 전송)

런타임 산출물(roster.json/inbox/outbox)은 gitignore. `.gitkeep` + 이 README 만 커밋 (ADR-012).
