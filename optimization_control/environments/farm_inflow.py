"""Farm entrance only: reuse Kaimal speed, add slow direction and background TI.

Not a full-field TurbSim implementation. No wake deficits or independent turbine
winds. Direction evolution is an explicit training design, not an IEC spectrum.
"""

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import numpy as np

from .wind_generator import WindConfig, generate_wind, SPLITS

REFERENCE = "https://openfast.readthedocs.io/en/main/_downloads/cb14d3e2d3533d76e405d730fea19846/TurbSim_v2.00.pdf"


@dataclass
class InflowTrace:
    time_s: np.ndarray
    values: np.ndarray
    components: np.ndarray
    metadata: dict

    def __post_init__(self):
        self.time_s = np.asarray(self.time_s, dtype=np.float64)
        self.values = np.asarray(self.values, dtype=np.float64)
        self.components = np.asarray(self.components, dtype=np.float64)
        n = len(self.time_s)
        if n < 2 or self.time_s.shape != (n,) or self.values.shape != (n, 3) or self.components.shape != (n, 3):
            raise ValueError("inflow requires time [N], speed/direction/TI [N,3] and components [N,3]")
        if not all(np.all(np.isfinite(a)) for a in (self.time_s, self.values, self.components)):
            raise ValueError("non-finite inflow")
        dt = self.metadata["dt_s"]
        if not np.isfinite(dt) or dt <= 0 or self.time_s[0] != 0 or not np.allclose(np.diff(self.time_s), dt):
            raise ValueError("invalid inflow time grid")
        if np.any(self.values[:, 0] <= 0) or np.any((self.values[:, 1] < 0) | (self.values[:, 1] >= 2*np.pi)) or np.any((self.values[:, 2] < 0) | (self.values[:, 2] >= 1)):
            raise ValueError("invalid speed/direction/TI")
        if not np.allclose(self.values[:, 0], self.components.sum(axis=1)):
            raise ValueError("inflow speed decomposition mismatch")

    def save(self, path):
        path = Path(path)
        if path.exists() or path.with_suffix(".json").exists():
            raise FileExistsError("inflow outputs are never overwritten")
        np.savetxt(path, np.column_stack((self.time_s, self.values, self.components)), delimiter=",", fmt="%.17g",
                   header="time_s,speed_m_s,direction_rad,background_ti,background_m_s,turbulence_m_s,event_m_s", comments="")
        meta = dict(self.metadata, csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        path.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path):
        path = Path(path)
        meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if meta.get("version") != "farm_entrance_v1" or hashlib.sha256(path.read_bytes()).hexdigest() != meta["csv_sha256"]:
            raise ValueError("inflow version or checksum mismatch")
        data = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
        if data.shape[1] != 7:
            raise ValueError("inflow requires seven CSV columns")
        return cls(data[:, 0], data[:, 1:4], data[:, 4:7], meta)


def generate_inflow(config, *, dt_s, horizon, seed=42, split="train", episode=0):
    speed_cfg = dict(config.get("speed", {}), dt_s=dt_s, duration_s=dt_s*horizon)
    trace = generate_wind(WindConfig(**speed_cfg), seed=seed, split=split, episode=episode)
    direction = config.get("direction", {})
    center = float(direction.get("mean_rad", 1.5*np.pi))
    amplitude = float(direction.get("amplitude_rad", .08))
    period = float(direction.get("period_s", 300.0))
    ramp = float(direction.get("ramp_rad", .04))
    if not all(np.isfinite(v) for v in (center, amplitude, period, ramp)) or amplitude < 0 or period <= 0:
        raise ValueError("invalid direction parameters")
    rng = np.random.default_rng(np.random.SeedSequence([seed, SPLITS[split], episode, 937]))
    phase = rng.uniform(0, 2*np.pi)
    t = trace.time_s
    progress = np.clip((t/(dt_s*horizon) - .2)/.6, 0, 1)
    trend = ramp*(3*progress**2-2*progress**3) if trace.metadata["scenario"] == "ramp" else 0
    theta = (center + amplitude*np.sin(2*np.pi*t/period + phase) + trend) % (2*np.pi)
    values = np.column_stack((trace.speed_m_s, theta, np.full_like(t, trace.metadata["ti_requested"])))
    meta = {"version": "farm_entrance_v1", "dt_s": dt_s, "seed": seed, "split": split,
            "episode": episode, "speed_metadata": trace.metadata, "direction_config": direction,
            "source": "synthetic_entrance_not_full_field", "reference": REFERENCE,
            "speed_semantics": "instantaneous band_limited entrance sample",
            "ti_semantics": "background spectral parameter, constant per episode, before ramp/gust",
            "direction_semantics": "shared angle convention with nacelle; smooth synthetic training design"}
    return InflowTrace(t, values, np.column_stack((trace.background_m_s, trace.turbulence_m_s, trace.event_m_s)), meta)
