from datetime import UTC, datetime, timedelta
from typing import Any

CETUS_TAG = "CetusSyndicate"
GHOUL_TAG = "InfestedPlains"
CETUS_NIGHT_SECONDS = 3000


class WorldStateSchemaError(ValueError):
    pass


def _epoch_seconds(value: object) -> int:
    if not isinstance(value, int):
        raise WorldStateSchemaError("WorldState Time must be integer epoch seconds")
    return value


def _bson_date(value: object) -> datetime:
    try:
        raw = value["$date"]["$numberLong"]  # type: ignore[index]
        result = datetime.fromtimestamp(int(raw) / 1000, tz=UTC)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise WorldStateSchemaError("invalid extended JSON date") from exc
    return result


def _bson_id(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    oid = value.get("$oid")
    return oid if isinstance(oid, str) and oid else None


def _objects(value: object, section: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise WorldStateSchemaError(f"{section} must be an array of objects")
    return value


class WarframeWorldStateAdapter:
    def extract(self, provider_key: str, payload: dict[str, Any]) -> dict[str, object]:
        extractors = {
            "warframe.cetus_night": self.cetus_night,
            "warframe.konzu_rotation": self.konzu_rotation,
            "warframe.ghoul_event": self.ghoul_event,
        }
        try:
            extractor = extractors[provider_key]
        except KeyError as exc:
            raise KeyError(f"unsupported WorldState provider: {provider_key}") from exc
        return extractor(payload)

    def extract_all(self, payload: dict[str, Any]) -> dict[str, dict[str, object]]:
        return {
            key: self.extract(key, payload)
            for key in (
                "warframe.cetus_night",
                "warframe.konzu_rotation",
                "warframe.ghoul_event",
            )
        }

    def cetus_night(self, payload: dict[str, Any]) -> dict[str, object]:
        observed_at = datetime.fromtimestamp(_epoch_seconds(payload.get("Time")), tz=UTC)
        mission = self._cetus_mission(payload)
        bounty_end = _bson_date(mission.get("Expiry")).replace(second=0, microsecond=0)
        seconds_to_night_end = (bounty_end - observed_at).total_seconds()
        if seconds_to_night_end <= 0:
            raise WorldStateSchemaError("Cetus bounty expiry is not in the future")
        is_night = seconds_to_night_end <= CETUS_NIGHT_SECONDS
        phase_end = bounty_end if is_night else bounty_end - timedelta(seconds=CETUS_NIGHT_SECONDS)
        phase = "night" if is_night else "day"
        return {
            "identity": f"cetus:{int(bounty_end.timestamp())}:{phase}",
            "is_night": is_night,
            "observed_at": observed_at,
            "effective_at": (
                bounty_end - timedelta(seconds=CETUS_NIGHT_SECONDS) if is_night else observed_at
            ),
            "expires_at": phase_end,
        }

    def konzu_rotation(self, payload: dict[str, Any]) -> dict[str, object]:
        observed_at = datetime.fromtimestamp(_epoch_seconds(payload.get("Time")), tz=UTC)
        mission = self._cetus_mission(payload)
        seed = mission.get("Seed")
        if not isinstance(seed, int):
            raise WorldStateSchemaError("Cetus Syndicate Seed must be an integer")
        activation = _bson_date(mission.get("Activation"))
        expiry = _bson_date(mission.get("Expiry"))
        return {
            "rotation_id": f"{seed}:{int(expiry.timestamp())}",
            "observed_at": observed_at,
            "effective_at": activation,
            "expires_at": expiry,
            "confirmed_summary": None,
        }

    def ghoul_event(self, payload: dict[str, Any]) -> dict[str, object]:
        observed_at = datetime.fromtimestamp(_epoch_seconds(payload.get("Time")), tz=UTC)
        goals = _objects(payload.get("Goals"), "Goals")
        candidates = [goal for goal in goals if goal.get("Tag") == GHOUL_TAG]
        for goal in candidates:
            activation = _bson_date(goal.get("Activation"))
            expiry = _bson_date(goal.get("Expiry"))
            active = activation <= observed_at < expiry and not bool(goal.get("Success"))
            if active:
                identity = _bson_id(goal.get("_id")) or (
                    f"ghoul:{int(activation.timestamp())}:{int(expiry.timestamp())}"
                )
                return {
                    "identity": identity,
                    "active": True,
                    "observed_at": observed_at,
                    "effective_at": activation,
                    "expires_at": expiry,
                }
        return {
            "identity": "ghoul:inactive",
            "active": False,
            "observed_at": observed_at,
            "effective_at": observed_at,
            "expires_at": None,
        }

    @staticmethod
    def _cetus_mission(payload: dict[str, Any]) -> dict[str, Any]:
        missions = _objects(payload.get("SyndicateMissions"), "SyndicateMissions")
        try:
            return next(mission for mission in missions if mission.get("Tag") == CETUS_TAG)
        except StopIteration as exc:
            raise WorldStateSchemaError("Cetus Syndicate mission is missing") from exc
