# Claude Status Monitor

Claude 서비스 상태를 5분마다 자동 체크하고, 이상 감지 시 Slack으로 알림을 발송합니다.

## 모니터링 대상

- claude.ai
- platform.claude.com
- Claude API (api.anthropic.com)
- Claude Code
- Claude for Government

## 알림 조건

- 전체 상태가 비정상 (minor / major / critical)
- 개별 서비스가 operational이 아닐 때
- 미해결 인시던트 존재 시

정상 상태일 경우 Slack 발송 없음

## 설치

```bash
pip install -r requirements.txt
```

## 설정

`.env` 파일 생성:

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
CHECK_INTERVAL=300
```

## 실행

```bash
python claude_status.py
```
