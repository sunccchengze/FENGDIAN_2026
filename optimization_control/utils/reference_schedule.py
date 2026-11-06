"""Versioned observation-coordinate speed reference with identical float32 ops."""
import numpy as np

LEGACY = "legacy_physical"
OBSERVATION = "observation_float32_v1"


def speed_numpy(obs, schedule):
    scale, slope, low, high = schedule
    value = np.asarray(obs, dtype=np.float32)[..., 1] * np.float32(scale)
    value = value * np.float32(slope)
    value = value - np.float32(low)
    value = np.float32(2) * value
    value = value / np.float32(high - low)
    return np.clip(value - np.float32(1), -1, 1).astype(np.float32)


def speed_torch(obs, schedule):
    import torch
    scale, slope, low, high = schedule
    return torch.clamp(2 * (obs[..., 1] * scale * slope - low) / (high - low) - 1, -1, 1)
