from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class PlatformRule:
    weight: float
    floor_current: float
    floor_abs_gain: float
    min_velocity: float
    min_abs_gain: float
    new_tiny_floor: float
    new_launch_floor: float


@dataclass(frozen=True)
class PipelineConfig:
    timezone: str
    expansion_top_n: int
    dual_platform_bonus: float
    platforms: dict[str, PlatformRule]
    broad_seeds: dict[str, list[str]]


@dataclass(frozen=True)
class ActorSpec:
    actor_id: str
    dataset_key: str
    result_format: str


@dataclass(frozen=True)
class ActorConfig:
    platforms: dict[str, ActorSpec]
    phase2: dict[str, ActorSpec]


def _read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_config(path: str | Path) -> PipelineConfig:
    payload = _read_json(path)
    platforms = {
        name: PlatformRule(**rule_payload)
        for name, rule_payload in payload["platforms"].items()
    }
    return PipelineConfig(
        timezone=payload["timezone"],
        expansion_top_n=payload["expansion_top_n"],
        dual_platform_bonus=payload["dual_platform_bonus"],
        platforms=platforms,
        broad_seeds=payload["broad_seeds"],
    )


def load_actor_config(path: str | Path) -> ActorConfig:
    payload = _read_json(path)
    platforms = {
        name: ActorSpec(**platform_payload)
        for name, platform_payload in payload.items()
        if name != "phase2"
    }
    phase2 = {
        name: ActorSpec(**platform_payload)
        for name, platform_payload in payload.get("phase2", {}).items()
    }
    return ActorConfig(platforms=platforms, phase2=phase2)
