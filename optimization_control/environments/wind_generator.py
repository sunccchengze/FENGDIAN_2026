"""Seeded, band-limited single-point longitudinal synthetic wind (not full-field).

Kaimal PSD: TurbSim v2 guide, spectral models, Eq. 23.
No per-record variance normalization or clipping: finite-record TI fluctuates.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json

import numpy as np
import yaml

SPLITS = {"train": 0, "validation": 1, "test": 2}


@dataclass(frozen=True)
class WindConfig:
    dt_s: float = 1.0
    duration_s: float = 600.0
    mean_min_m_s: float = 6.0
    mean_max_m_s: float = 10.0
    ti_values: tuple = (0.06, 0.08, 0.10)
    length_scale_m: float = 100.0
    padding_factor: int = 8
    scenario: str = "mixed"
    ramp_amplitude_m_s: float = 1.0
    gust_amplitude_m_s: float = 1.5
    gust_duration_s: float = 40.0
    speed_min_m_s: float = 0.5
    speed_max_m_s: float = 16.0
    max_attempts: int = 100

    def __post_init__(self):
        positive = (self.dt_s, self.duration_s, self.mean_min_m_s,
                    self.mean_max_m_s, self.length_scale_m, self.gust_duration_s,
                    self.speed_min_m_s, self.speed_max_m_s)
        if not all(np.isfinite(x) and x > 0 for x in positive):
            raise ValueError("positive finite wind parameters required")
        if self.mean_min_m_s > self.mean_max_m_s:
            raise ValueError("mean range reversed")
        if not self.speed_min_m_s < self.mean_min_m_s <= self.mean_max_m_s < self.speed_max_m_s:
            raise ValueError("mean range must lie inside operating envelope")
        if not self.ti_values or any(not np.isfinite(x) or not 0 <= x < 1 for x in self.ti_values):
            raise ValueError("TI must lie in [0,1)")
        if self.scenario not in ("stationary", "ramp", "gust", "mixed"):
            raise ValueError("unknown wind scenario")
        if any(not np.isfinite(x) or x < 0 for x in (self.ramp_amplitude_m_s, self.gust_amplitude_m_s)):
            raise ValueError("event amplitudes must be finite and nonnegative")
        if self.gust_duration_s > self.duration_s / 2:
            raise ValueError("gust must fit inside the episode")
        for x in (self.padding_factor, self.max_attempts):
            if isinstance(x, bool) or not isinstance(x, int) or x < 1:
                raise ValueError("padding and attempts must be positive integers")
        if self.padding_factor < 2:
            raise ValueError("padding_factor must be >=2 to avoid episode periodicity")
        if self.steps < 32 or not np.isclose(self.steps * self.dt_s, self.duration_s):
            raise ValueError("duration must be an integer number of >=32 time steps")

    @property
    def steps(self):
        return int(round(self.duration_s / self.dt_s))


def load_config(path):
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if config.get("version") != "stochastic_single_v2" or config.get("seed") != 42:
        raise ValueError("requires stochastic_single_v2 config with master seed 42")
    WindConfig(**config["wind"])
    return config


def kaimal_psd(f, mean_m_s, sigma_m_s, length_scale_m):
    f = np.asarray(f)
    return (4 * sigma_m_s**2 * length_scale_m / mean_m_s
            / (1 + 6 * f * length_scale_m / mean_m_s)**(5 / 3))


@dataclass
class WindTrace:
    time_s: np.ndarray
    speed_m_s: np.ndarray
    background_m_s: np.ndarray
    turbulence_m_s: np.ndarray
    event_m_s: np.ndarray
    metadata: dict

    def __post_init__(self):
        arrays = (self.time_s, self.speed_m_s, self.background_m_s,
                  self.turbulence_m_s, self.event_m_s)
        if any(np.asarray(a).ndim != 1 or len(a) != len(self.time_s)
               or not np.all(np.isfinite(a)) for a in arrays):
            raise ValueError("trace arrays must be finite, 1D and equally sized")
        if len(self.time_s) < 2 or self.time_s[0] != 0 or np.any(self.speed_m_s <= 0):
            raise ValueError("invalid trace time or speed")
        if not np.allclose(np.diff(self.time_s), self.metadata["config"]["dt_s"]):
            raise ValueError("trace must have uniform configured time steps")
        if not np.allclose(self.speed_m_s, self.background_m_s + self.turbulence_m_s + self.event_m_s):
            raise ValueError("trace decomposition mismatch")
        c = WindConfig(**self.metadata["config"])
        if len(self.time_s) != c.steps + 1:
            raise ValueError("trace length differs from config")
        if np.any(self.speed_m_s < c.speed_min_m_s) or np.any(self.speed_m_s > c.speed_max_m_s):
            raise ValueError("trace outside configured envelope")

    def save(self, path):
        path = Path(path)
        if path.exists() or path.with_suffix(".json").exists():
            raise FileExistsError("refusing to overwrite a wind trace")
        data = np.column_stack((self.time_s, self.speed_m_s, self.background_m_s,
                                self.turbulence_m_s, self.event_m_s))
        np.savetxt(path, data, delimiter=",", fmt="%.17g", comments="",
                   header="time_s,speed_m_s,background_m_s,turbulence_m_s,event_m_s")
        metadata = dict(self.metadata, csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path):
        path = Path(path)
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["csv_sha256"]:
            raise ValueError("wind CSV checksum mismatch")
        data = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
        if data.shape[1] != 5:
            raise ValueError("wind CSV requires five columns")
        return cls(*(data[:, i] for i in range(5)), metadata)


def generate_wind(config, *, seed=42, split="train", worker=0, episode=0):
    if split not in SPLITS:
        raise ValueError("unknown split")
    for value in (seed, worker, episode):
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
            raise ValueError("seed, worker and episode must be nonnegative integers")
    rng = np.random.default_rng(np.random.SeedSequence([seed, SPLITS[split], worker, episode]))
    c = config
    # Cycle across four strata; draw inside each stratum using independent streams.
    stratum = (episode + worker) % 4
    mean = c.mean_min_m_s + (stratum + rng.random()) / 4 * (c.mean_max_m_s - c.mean_min_m_s)
    ti = float(rng.choice(c.ti_values))
    scenario = str(rng.choice(["stationary", "ramp", "gust"])) if c.scenario == "mixed" else c.scenario
    t = np.arange(c.steps + 1, dtype=np.float64) * c.dt_s
    background = np.full_like(t, mean)
    event = np.zeros_like(t)
    if scenario == "ramp":
        phase = np.clip((t / c.duration_s - 0.2) / 0.6, 0, 1)
        background += rng.choice([-1, 1]) * c.ramp_amplitude_m_s * (3 * phase**2 - 2 * phase**3)
    elif scenario == "gust":
        start = rng.uniform(0.2 * c.duration_s, 0.8 * c.duration_s - c.gust_duration_s)
        phase = (t - start) / c.gust_duration_s
        mask = (phase >= 0) & (phase <= 1)
        event[mask] = c.gust_amplitude_m_s * 0.5 * (1 - np.cos(2 * np.pi * phase[mask]))
    n = c.padding_factor * (c.steps + 1)
    n += n % 2
    f = np.fft.rfftfreq(n, c.dt_s)
    psd = kaimal_psd(f, mean, mean * ti, c.length_scale_m)
    # Expected one-sided periodogram equals S(f). DC=0; correct real Nyquist bin.
    # Frequencies above Nyquist are omitted, not aliased or variance-renormalized.
    df = 1 / (n * c.dt_s)
    expected_variance = float(np.sum(psd[1:-1]) * df + psd[-1] * df)
    for attempt in range(c.max_attempts):
        coeff = (rng.normal(size=len(f)) + 1j * rng.normal(size=len(f))) * np.sqrt(n / c.dt_s * psd / 4)
        coeff[0] = 0
        coeff[-1] = rng.normal() * np.sqrt(n / c.dt_s * psd[-1])
        full = np.fft.irfft(coeff, n=n)
        start = int(rng.integers(0, n - len(t) + 1))
        turbulence = full[start:start + len(t)]
        speed = background + turbulence + event
        if np.all((speed >= c.speed_min_m_s) & (speed <= c.speed_max_m_s)):
            break
    else:
        raise ValueError("wind envelope rejection exhausted; revise configuration")
    return WindTrace(t, speed, background, turbulence, event, {
        "version": "kaimal_single_point_v1", "config": asdict(c),
        "seed": int(seed), "split": split, "worker": int(worker), "episode": int(episode),
        "mean_m_s": float(mean), "ti_requested": ti, "scenario": scenario,
        "rejected_attempts": attempt, "expected_band_variance_m2_s2": expected_variance,
        "source": "synthetic_assumption", "ti_semantics": "stationary background component, before events",
    })
