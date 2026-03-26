"""Claude 서비스 상태 모니터링 도구 (Slack 알림 지원)"""

import os
import time
import signal
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

load_dotenv()

BASE_URL = "https://status.claude.com/api/v2"
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 3600))  # 기본 1시간(초)

console = Console()

STATUS_STYLE = {
    "operational": ("green", "Operational"),
    "degraded_performance": ("yellow", "Degraded"),
    "partial_outage": ("dark_orange", "Partial Outage"),
    "major_outage": ("red", "Major Outage"),
    "under_maintenance": ("blue", "Maintenance"),
}

INDICATOR_STYLE = {
    "none": ("green", "All Systems Operational"),
    "minor": ("yellow", "Minor Issues"),
    "major": ("dark_orange", "Major Issues"),
    "critical": ("red", "Critical Outage"),
}

IMPACT_EMOJI = {
    "none": ":large_green_circle:",
    "minor": ":warning:",
    "major": ":orange_circle:",
    "critical": ":red_circle:",
}

STATUS_EMOJI = {
    "operational": ":large_green_circle:",
    "degraded_performance": ":warning:",
    "partial_outage": ":orange_circle:",
    "major_outage": ":red_circle:",
    "under_maintenance": ":wrench:",
}


def fetch_json(endpoint: str) -> dict:
    resp = requests.get(f"{BASE_URL}/{endpoint}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def send_slack(blocks: list):
    if not SLACK_WEBHOOK_URL or not SLACK_WEBHOOK_URL.startswith("https://"):
        console.print("[red]Slack Webhook URL이 설정되지 않았습니다.[/]")
        return

    payload = {"blocks": blocks}
    resp = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
    if resp.status_code == 200:
        console.print("[green]Slack 알림 발송 완료[/]")
    else:
        console.print(f"[red]Slack 발송 실패: {resp.status_code} {resp.text}[/]")


def build_slack_message(overall: dict, down_components: list, incidents: list) -> list:
    """이상 발생 시 Slack 메시지 블록 생성"""
    indicator = overall["status"]["indicator"]
    emoji = IMPACT_EMOJI.get(indicator, ":question:")
    _, label = INDICATOR_STYLE.get(indicator, ("white", indicator))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} Claude Status Alert"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*상태:* {label}\n*확인 시각:* {now}"}
        },
    ]

    # 비정상 컴포넌트
    if down_components:
        comp_lines = []
        for comp in down_components:
            s_emoji = STATUS_EMOJI.get(comp["status"], ":question:")
            _, s_label = STATUS_STYLE.get(comp["status"], ("white", comp["status"]))
            comp_lines.append(f"{s_emoji} *{comp['name']}* - {s_label}")
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*비정상 서비스*\n" + "\n".join(comp_lines)}
        })

    # 인시던트
    if incidents:
        for inc in incidents:
            i_emoji = IMPACT_EMOJI.get(inc["impact"], ":warning:")
            latest_msg = ""
            if inc.get("incident_updates"):
                latest_msg = f"\n> {inc['incident_updates'][0]['body']}"
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{i_emoji} *Incident: {inc['name']}*\n"
                        f"Impact: `{inc['impact']}` | Status: `{inc['status']}`\n"
                        f"Started: {inc['created_at']}{latest_msg}"
                    )
                }
            })

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "<https://status.claude.com|status.claude.com>"}]
    })

    return blocks


def check_and_notify():
    """이상 유무 확인 후 문제가 있으면 Slack 발송"""
    overall = fetch_json("status.json")
    components = fetch_json("components.json")
    incidents_data = fetch_json("incidents/unresolved.json")

    # 비정상 컴포넌트 필터링
    down_components = [
        c for c in components["components"]
        if c["status"] != "operational" and c.get("group") is not True
    ]
    incidents = incidents_data["incidents"]

    has_issue = overall["status"]["indicator"] != "none" or down_components or incidents

    if has_issue:
        console.print("[yellow]이상 감지 → Slack 알림 발송[/]")
        blocks = build_slack_message(overall, down_components, incidents)
        send_slack(blocks)
    else:
        console.print("[green]정상 상태 → Slack 알림 없음[/]")

    return has_issue


def show_overall_status():
    data = fetch_json("status.json")
    indicator = data["status"]["indicator"]
    color, label = INDICATOR_STYLE.get(indicator, ("white", indicator))
    console.print(Panel(f"[bold {color}]{label}[/]", title="Claude Status", border_style=color))


def show_components():
    data = fetch_json("components.json")
    table = Table(title="Components", show_lines=True)
    table.add_column("Service", style="bold")
    table.add_column("Status", justify="center")

    for comp in data["components"]:
        if comp.get("group") is True:
            continue
        status = comp["status"]
        color, label = STATUS_STYLE.get(status, ("white", status))
        table.add_row(comp["name"], f"[{color}]{label}[/]")

    console.print(table)


def show_incidents():
    data = fetch_json("incidents/unresolved.json")
    incidents = data["incidents"]

    if not incidents:
        console.print("\n[green]No unresolved incidents.[/]\n")
        return

    for inc in incidents:
        color = "yellow" if inc["impact"] == "minor" else "red"
        console.print(f"\n[bold {color}]Incident: {inc['name']}[/]")
        console.print(f"  Impact: {inc['impact']}  |  Status: {inc['status']}")
        console.print(f"  Started: {inc['created_at']}")

        if inc.get("incident_updates"):
            latest = inc["incident_updates"][0]
            console.print(f"  Latest update: {latest['body']}")


def show_maintenance():
    data = fetch_json("scheduled-maintenances/upcoming.json")
    maintenances = data["scheduled_maintenances"]

    if not maintenances:
        console.print("[green]No upcoming maintenance.[/]\n")
        return

    table = Table(title="Upcoming Maintenance")
    table.add_column("Name")
    table.add_column("Scheduled For")
    table.add_column("Status")

    for m in maintenances:
        table.add_row(m["name"], m["scheduled_for"], m["status"])

    console.print(table)


def run_check():
    console.print(f"\n[dim]{'=' * 50}[/]")
    console.print(f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]\n")

    try:
        show_overall_status()
        show_components()
        show_incidents()
        show_maintenance()
        console.print()
        check_and_notify()
    except requests.RequestException as e:
        console.print(f"[red]Error fetching status: {e}[/]")


def main():
    # --once 옵션: 1회 실행 후 종료 (GitHub Actions용)
    once = "--once" in sys.argv

    if once:
        run_check()
    else:
        signal.signal(signal.SIGINT, lambda *_: (console.print("\n[dim]모니터링 종료[/]"), sys.exit(0)))
        console.print(f"[bold cyan]Claude Status Monitor 시작[/]")
        console.print(f"[dim]체크 간격: {CHECK_INTERVAL // 60}분 | Ctrl+C로 종료[/]")

        while True:
            run_check()
            console.print(f"\n[dim]다음 체크: {CHECK_INTERVAL // 60}분 후...[/]")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
