"""Apply the environment's float32 wind contract to the frozen pilot reporter.

The originally locked reporter and training sources remain byte-identical.
Only saved disturbance comparisons use the same float32 cast as env.reset.
"""
from . import yaw_pilot_report as frozen


def report():
    import numpy as np
    original = frozen.read_eval

    def read_physical(ref, cases, arm):
        physical = [(case, wind.astype(np.float32)) for case, wind in cases]
        return original(ref, physical, arm)

    frozen.read_eval = read_physical
    try:
        frozen.report()
    finally:
        frozen.read_eval = original


if __name__ == "__main__":
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(frozen.old.ORIGIN/".venv/pinn_tf216")
    report()
