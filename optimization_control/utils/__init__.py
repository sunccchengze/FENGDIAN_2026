"""Reusable optimization-side control components.

These modules deliberately do not depend on Gymnasium, PyTorch, or a concrete
PINN implementation.  They form the stable seam between a policy and any
quasi-static/dynamic plant adapter.
"""

from .action_mapper import (
    ActionChannelConfig,
    ActionMapper,
    ActionMapperConfig,
    ActionMappingResult,
    ActionNormalizationResult,
    ParameterSource,
)
from .actuator_model import (
    ActuatorChannelConfig,
    ActuatorModel,
    ActuatorModelConfig,
    ActuatorStepResult,
)
from .reference_power import (
    ReferencePowerConfig,
    ReferencePowerGenerator,
    ReferencePowerStepResult,
)
from .reward import RewardConfig, RewardCalculator, RewardResult
from .state_pipeline import (
    AssembledState,
    ObservationBuilder,
    ObservationConfig,
    ObservationFeatureConfig,
    StateAssembler,
    StateAssemblerConfig,
)

__all__ = [
    "ActionChannelConfig",
    "ActionMapper",
    "ActionMapperConfig",
    "ActionMappingResult",
    "ActionNormalizationResult",
    "ActuatorChannelConfig",
    "ActuatorModel",
    "ActuatorModelConfig",
    "ActuatorStepResult",
    "AssembledState",
    "ObservationBuilder",
    "ObservationConfig",
    "ObservationFeatureConfig",
    "ParameterSource",
    "ReferencePowerConfig",
    "ReferencePowerGenerator",
    "ReferencePowerStepResult",
    "RewardConfig",
    "RewardCalculator",
    "RewardResult",
    "StateAssembler",
    "StateAssemblerConfig",
]
