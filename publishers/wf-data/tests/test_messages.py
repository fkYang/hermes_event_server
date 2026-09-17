import json
from pathlib import Path
from zoneinfo import ZoneInfo

from wfdata_publisher.messages import render
from wfdata_publisher.source import parse_window

FIXTURE = Path(__file__).parent / "fixtures" / "tent-bounties.sample.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def window_for(section: str):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if section == "next":
        payload["next"] = {
            "activation": "2026-09-17T14:18:50.647+08:00",
            "expiry": "2026-09-17T16:48:49.000+08:00",
            "tentA": {"jobs": [{"id": "RescueBountyResc", "nameZh": "搜索并救援"}]},
        }
    return parse_window(payload, section)


def test_current_message_uses_local_time_and_chinese_labels() -> None:
    message = render(window_for("current"), timezone=SHANGHAI, lead_seconds=300)
    assert message["title"] == "Cetus 赏金轮换"
    assert message["text"].startswith("当前轮次包含：刺杀指挥官")
    assert "时段：09-17 11:48 → 09-17 14:18（UTC+08:00）" in message["text"]
    assert message["template_key"] == "warframe.cetus.bounty_current.default"
    assert message["data"]["activation"] == "2026-09-17T03:48:51Z"


def test_next_message_states_the_lead_time() -> None:
    message = render(window_for("next"), timezone=SHANGHAI, lead_seconds=300)
    assert message["title"] == "Cetus 赏金预告"
    assert message["text"].startswith("下一轮包含：搜索并救援")
    assert "开始：09-17 14:18，约 5 分钟后（UTC+08:00）" in message["text"]
    assert message["template_key"] == "warframe.cetus.bounty_next.default"
