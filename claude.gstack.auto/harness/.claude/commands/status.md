# /project:status — 프로젝트 현황 대시보드

프로젝트의 전체 진행 상황을 한눈에 확인한다.

## 실행

다음을 순서대로 실행하고 결과를 정리하여 출력:

```bash
# 1. 기능 완료 현황 (python3 사용)
python3 - << 'EOF'
import json, sys

try:
    with open('feature_list.json') as f:
        features = json.load(f)
except FileNotFoundError:
    print("❌ feature_list.json 파일이 없습니다.")
    sys.exit(1)

total = len(features)
done  = sum(1 for f in features if f.get('passes'))

priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
by_priority = {}
for feat in features:
    p = feat.get('priority', 'low')
    by_priority.setdefault(p, {'total': 0, 'done': 0})
    by_priority[p]['total'] += 1
    if feat.get('passes'):
        by_priority[p]['done'] += 1

pct = round(done / total * 100) if total else 0
print(f"\n📊 전체 진행률: {done}/{total} ({pct}%)")
print("─" * 40)

icons = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}
for p in ['critical', 'high', 'medium', 'low']:
    if p in by_priority:
        s = by_priority[p]
        print(f"  {icons[p]} {p.capitalize():8}: {s['done']}/{s['total']}")

# 미완료 목록 (우선순위 + status 포함)
pending = [f for f in features if not f.get('passes')]
pending.sort(key=lambda f: priority_order.get(f.get('priority','low'), 99))

if pending:
    print(f"\n📋 미완료 기능 ({len(pending)}개)")
    print("─" * 40)
    status_icons = {
        'todo':        '⬜',
        'in-progress': '🔄',
        'review':      '👀',
        'qa':          '🧪',
    }
    for f in pending:
        st = f.get('status', 'todo')
        icon = status_icons.get(st, '⬜')
        print(f"  {icon} [{f.get('priority','?').upper():8}] {f['id']}: {f['title']} ({st})")
else:
    print("\n🎉 모든 기능이 완료되었습니다!")

EOF

# 2. 최근 커밋 내역
echo ""
echo "🕐 최근 커밋"
echo "─────────────────────────────────────────"
git log --oneline -10

# 3. 마지막 인계 내용
echo ""
echo "📝 마지막 인계 내용"
echo "─────────────────────────────────────────"
tail -25 claude-progress.txt
```
