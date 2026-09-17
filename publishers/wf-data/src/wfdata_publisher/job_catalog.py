"""Controlled catalogue of Cetus bounty jobs.

These keys are the `jobId` values reported by the wf-data service. The event
catalogue JSON files must declare exactly this list as `match_key_options`, and
the regression test in `tests/test_job_catalog.py` enforces that they stay in
sync. Adding a job here is a deployment configuration change, never a user
operation.
"""

from __future__ import annotations

JOB_LABELS: dict[str, str] = {
    "AssassinateBountyAss": "刺杀指挥官",
    "AssassinateBountyCap": "捕获新任 Grineer 指挥官",
    "AttritionBountySab": "破坏 Grineer 补给线",
    "AttritionBountyLib": "削弱 Grineer 据点",
    "AttritionBountyCap": "捕获他们的领袖",
    "AttritionBountyExt": "宰杀敌人",
    "ReclamationBountyCap": "捕获 Grineer 特工",
    "ReclamationBountyTheft": "取回被偷的器物",
    "ReclamationBountyCache": "找出遗失的器物",
    "CaptureBountyCapOne": "捕获 Grineer 指挥官",
    "CaptureBountyCapTwo": "间谍捕手",
    "SabotageBountySab": "破坏原型机",
    "RescueBountyResc": "搜索并救援",
}


def label_for(job_key: str) -> str:
    return JOB_LABELS.get(job_key, job_key)


def catalog_options() -> list[dict[str, str]]:
    return [{"key": key, "label": label} for key, label in JOB_LABELS.items()]
