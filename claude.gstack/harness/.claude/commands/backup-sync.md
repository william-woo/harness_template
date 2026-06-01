# /project:backup-sync — 다운스트림 백업 동기화

다운스트림 프로젝트의 하네스 엔지니어링 산출물 (`src/` 제외) 을 백업 리포에 동기화한다.
**옵셔널** — 호출하지 않으면 하네스 동작에 영향 없음.

## 사용법

```
/project:backup-sync               # 기본 동작 = sync
/project:backup-sync init          # 백업 리포·브랜치 초기 설정 (세션 2 예정)
/project:backup-sync status        # 마지막 sync 정보 + 변경 미리보기 (세션 2 예정)
/project:backup-sync config show   # 현재 설정 조회 (세션 2 예정)
/project:backup-sync self          # 셀프 dry-run — 의존성 체크 (세션 2 예정)
```

### 플래그

| 플래그 | 기본값 | 설명 |
|---|---|---|
| `--dry-run` | OFF | 실제 push 없이 미리보기만 |
| `--strict` | OFF | 에러 발생 시 exit 1 (CI gate용) |
| `--message` | 자동 | 커밋 메시지 override |
| `--format` | human | 출력 형식: human \| json |

## 헬퍼 스크립트

```bash
python3 .claude/bin/backup.py sync
python3 .claude/bin/backup.py sync --dry-run
python3 .claude/bin/backup.py self          # 의존성 빠른 확인
```

## 사전 설정 필요

`.claude/host.json` 에 `backup` 객체 추가:

```json
{
  "agent_type": "claude-code",
  "harness_version": 2,
  "backup": {
    "repo": "git@github.com:USER/REPO.git",
    "branch": "PROJECT-SLUG"
  }
}
```

- `backup.repo`: SSH URL 권장 (`git@github.com:user/repo.git`)
- `backup.branch`: 비워두면 `git remote` basename 자동 추출

`init` 서브커맨드로 설정 안내 (세션 2 구현): `python3 .claude/bin/backup.py init`

## 동작

1. `host.json` 의 `backup.repo` / `backup.branch` 로드
2. 보안 BLOCK 패턴 사전 검사 (`.env*`, `*.pem`, `*.key` 등) — 발견 시 차단 + exit 1
3. 임시 디렉토리에 백업 리포 clone
4. `backup.branch` checkout (없으면 orphan branch 신규 생성)
5. rsync — 제외 목록 적용 (아래 참조)
6. `git commit` + `git push origin <branch>` (ff-only)
7. `host.json` 의 `backup.last_sync` / `backup.last_sync_commit` 갱신

## 기본 제외 목록 (ADR-005 결정 6)

| 카테고리 | 패턴 |
|---|---|
| 사용자 코드 | `src/` |
| 빌드 산출물 | `node_modules/`, `__pycache__/`, `*.pyc`, `.venv/`, `dist/`, `build/`, `target/`, `.next/`, `out/` |
| 보안 (BLOCK) | `.env`, `.env.*`, `*.pem`, `*.key`, `credentials.json`, `.aws/` |
| IDE / OS | `.vscode/`, `.idea/`, `.DS_Store`, `*.swp`, `*.swo` |
| 로그 | `*.log`, `logs/`, `npm-debug.log*` |
| 서브 git 보호 | `.git/` |
| 세션 로컬 상태 | `freeze-dir.txt`, `lint-last.json`, `backup-last.json` |
| Binary state | `qa-browser/screenshots/`, `qa-browser/runs/` |
| 메타 하네스 전용 | `src/harness_template/` (이 프로젝트에서만 추가 제외) |

## 안전 보장 (ADR-005 결정 5)

- force push 절대 없음 (`--force` / `--force-with-lease` 미사용)
- ff-only push — 원격이 앞서 있으면 사용자에게 보고 + exit 0
- 네트워크/인증 실패 시 친절한 안내 + exit 0 (hook-failure-tolerance)
- 보안 BLOCK (.env 등) 만 예외적으로 exit 1 (자격증명 노출 방지)
- 재시도 0회 — 실패 즉시 진단 메시지 출력

## 인증 (ADR-005 결정 4)

- **SSH 권장**: `git@github.com:user/repo.git` — `ssh-agent` 사전 등록 필요
- **HTTPS 허용**: 안내 메시지 출력 후 계속 진행 (`.netrc` 또는 `GH_TOKEN` 사전 설정 필요)

SSH 인증 확인:
```bash
ssh-add -l           # ssh-agent 등록 확인
ssh -T git@github.com  # GitHub 연결 테스트
```

## 세션 분할 (F010)

| 세션 | 범위 | 상태 |
|---|---|---|
| 세션 1 (현재) | `sync` 코어 + 보안 BLOCK + `/project:backup-sync` 커맨드 | 구현 완료 |
| 세션 2 | `init` / `status` / `config` / `self` + `init-project` 안내 | 예정 |
| 세션 3 (선택) | CLAUDE.md 통합 + 에러 시나리오 dry-run + 최종 미러 정합 | 예정 |

## 설계 근거

- ADR-005: 다운스트림 백업 동기화 결정 1~9 전체
- F006 host.json SSOT 확장 (backup 객체)
- F005/F009 hook-failure-tolerance + 옵셔널 보장 패턴 일관

## 파일 위치

| 파일 | 역할 |
|---|---|
| `.claude/commands/backup-sync.md` | 이 파일 — 진입점·실행 절차 |
| `.claude/bin/backup.py` | 헬퍼 스크립트 (단일 파일, Python stdlib) |
| `docs/adr/ADR-005-downstream-backup-sync.md` | 설계 결정 근거 |
| `.claude/host.json` | `backup` 설정 저장 위치 (F006 SSOT 확장) |
| `.claude/state/backup-last.json` | 마지막 sync 캐시 (gitignore) |
