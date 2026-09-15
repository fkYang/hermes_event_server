from eventserver.providers.warframe.client import WarframeWorldStateClient


def safe_date(value: object) -> str:
    if isinstance(value, dict):
        if "$date" in value:
            return safe_date(value["$date"])
        if "$numberLong" in value:
            return f"epoch_ms:{value['$numberLong']}"
        return "{" + ",".join(sorted(value)) + "}"
    return f"{type(value).__name__}:{value}"


def main() -> None:
    payload = WarframeWorldStateClient().fetch()
    print("top_level_keys=" + ",".join(sorted(payload)))
    for section in ("SyndicateMissions", "Goals", "Events", "HubEvents"):
        value = payload.get(section)
        if isinstance(value, list):
            keys = sorted({key for item in value[:10] if isinstance(item, dict) for key in item})
            print(f"section={section}; count={len(value)}; item_keys={','.join(keys)}")
        else:
            print(f"section={section}; type={type(value).__name__}")
    print(f"world_time={safe_date(payload.get('Time'))}")
    for mission in payload.get("SyndicateMissions", []):
        if isinstance(mission, dict) and mission.get("Tag") in {
            "CetusSyndicate",
            "SolarisSyndicate",
            "EntratiSyndicate",
        }:
            print(
                "syndicate="
                f"{mission.get('Tag')}; id_type={type(mission.get('_id')).__name__}; "
                f"seed={mission.get('Seed')}; activation={safe_date(mission.get('Activation'))}; "
                f"expiry={safe_date(mission.get('Expiry'))}"
            )
    for goal in payload.get("Goals", []):
        if isinstance(goal, dict):
            jobs = goal.get("Jobs")
            job_keys = (
                sorted({key for item in jobs if isinstance(item, dict) for key in item})
                if isinstance(jobs, list)
                else []
            )
            print(
                f"goal_tag={goal.get('Tag')}; desc={goal.get('Desc')}; node={goal.get('Node')}; "
                f"activation={safe_date(goal.get('Activation'))}; "
                f"expiry={safe_date(goal.get('Expiry'))}; "
                f"count={goal.get('Count')}; goal={goal.get('Goal')}; "
                f"health={goal.get('HealthPct')}; success={goal.get('Success')}; "
                f"jobs={len(jobs) if isinstance(jobs, list) else 0}; "
                f"job_keys={','.join(job_keys)}"
            )


if __name__ == "__main__":
    main()
