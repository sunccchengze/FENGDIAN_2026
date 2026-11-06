"""Complete the immutable reporter with scalar-safe JSON and exact output reuse.

The frozen inference sources remain unchanged. This repairs reporting only;
existing partial outputs must be byte-identical, and no plant is constructed.
"""
import json
from types import SimpleNamespace

from . import nrel_speed_transfer as run
from . import nrel_speed_transfer_report as frozen


def plain(value):
    import numpy as np
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


class SavedStore(run.old.Store):
    def write(self, name, data, limit=None):
        path = (self.folder/name).resolve()
        if not path.is_relative_to(self.folder.resolve()):
            raise ValueError("report escaped experiment")
        if path.exists():
            payload = bytes(data)
            if path.read_bytes() != payload:
                raise ValueError("existing report differs: " + str(path))
            return dict(path=str(path), sha256=run.old.sha(path), bytes=len(payload))
        return super().write(name, data, limit)

    def json(self, name, value):
        return super().json(name, plain(value))


def report():
    run.context()
    original_store, original_json = run.store, frozen.json
    run.store = lambda: SavedStore(run.ROOT, 128*run.MIB)
    frozen.json = SimpleNamespace(dumps=lambda value, **kwargs: json.dumps(plain(value), **kwargs))
    try:
        frozen.performance()
    finally:
        run.store, frozen.json = original_store, original_json


if __name__ == "__main__":
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(run.old.ORIGIN/".venv/pinn_tf216")
    report()
