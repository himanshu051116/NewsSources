import importlib.util
import sys
from pathlib import Path


MODULE = Path(__file__).resolve().parents[3] / "scripts" / "smoke-load.py"
spec = importlib.util.spec_from_file_location("smoke_load", MODULE)
assert spec and spec.loader
smoke_load = importlib.util.module_from_spec(spec)
sys.modules["smoke_load"] = smoke_load
spec.loader.exec_module(smoke_load)


def test_percentile_uses_conservative_nearest_rank() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert smoke_load.percentile(values, 0.5) == 30.0
    assert smoke_load.percentile(values, 0.95) == 50.0
