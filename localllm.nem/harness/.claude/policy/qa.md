추론을 끝냈으면 반드시 bash 도구로 판정을 기록하고 답을 마쳐라. 산문 설명만으로는 판정이 성립하지 않는다.
기록 명령: `python3 .claude/bin/verify_loop.py record <FEATURE> --grader qa --verdict pass|revision --notes '<근거 한 줄>'`
인수 기준을 하나라도 확인하지 못했으면 revision 으로 기록하라.
추론은 짧게, 도구 호출은 확실하게 — 추론이 길어지면 기록할 지면이 남지 않는다.
