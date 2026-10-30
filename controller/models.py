from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

class ExperimentRequest(BaseModel):
    name: str = Field(default="manual", min_length=1, max_length=120)
    runtimes: list[str] = Field(default_factory=lambda: ["mf"])
    session_levels: list[int] = Field(default_factory=lambda: [500])
    action_rate: int = Field(default=10_000, ge=0)
    tick_rate: int = Field(default=50, ge=1, le=120)
    publication_rate: int = Field(default=20, ge=1, le=120)
    workers: int = Field(default=4, ge=1, le=128)
    capacity: int = Field(default=2048, ge=1)
    budget: int = Field(default=256, ge=1)
    warmup_seconds: int = Field(default=120, ge=0)
    measurement_seconds: int = Field(default=180, ge=1)
    repetitions: int = Field(default=10, ge=1, le=100)
    producer_threads: int = Field(default=2, ge=1, le=64)
    sample_interval_ms: int = Field(default=1000, ge=100, le=10_000)
    randomize_order: bool = True
    order_seed: int = 20261105
    mode: str = Field(default="factorial", pattern="^(factorial|aa)$")

    @model_validator(mode="after")
    def validate_plan(self):
        allowed = {"mf", "s1", "s2", "pekko"}
        unknown = [x for x in self.runtimes if x not in allowed]
        if unknown:
            raise ValueError(f"unknown runtime(s): {', '.join(unknown)}")
        if not self.runtimes:
            raise ValueError("at least one runtime is required")
        if not self.session_levels or any(v < 1 for v in self.session_levels):
            raise ValueError("session_levels must contain positive integers")
        return self

DEFAULTS = ExperimentRequest()

PRESETS: dict[str, dict] = {
    "smoke": ExperimentRequest(name="smoke", runtimes=["mf","s1","s2","pekko"], session_levels=[50,100], action_rate=2_000, warmup_seconds=5, measurement_seconds=10, repetitions=1, randomize_order=False).model_dump(),
    "aa": ExperimentRequest(name="aa-mf-500", runtimes=["mf"], session_levels=[500], action_rate=10_000, warmup_seconds=30, measurement_seconds=60, repetitions=10, mode="aa").model_dump(),
    "full": ExperimentRequest(name="thesis-full", runtimes=["mf","s1","s2","pekko"], session_levels=[100,250,500,750,875,1000,1125], action_rate=10_000, warmup_seconds=120, measurement_seconds=180, repetitions=10, randomize_order=True, order_seed=20261105).model_dump(),
}
