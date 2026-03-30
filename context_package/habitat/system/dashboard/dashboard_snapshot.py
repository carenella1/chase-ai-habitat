import json
import os


SNAPSHOT_PATH = "data/dashboard_snapshot.json"


def _safe(obj):

    try:
        import numpy as np

        if isinstance(obj, np.integer):
            return int(obj)

        if isinstance(obj, np.floating):
            return float(obj)

    except Exception:
        pass

    return obj


class DashboardSnapshot:

    def __init__(self):
        os.makedirs("data", exist_ok=True)

    def write_snapshot(self, data):

        safe_data = self._convert(data)

        with open(SNAPSHOT_PATH, "w") as f:
            json.dump(safe_data, f, indent=2)

    def _convert(self, obj):

        if isinstance(obj, dict):
            return {k: self._convert(v) for k, v in obj.items()}

        if isinstance(obj, list):
            return [self._convert(v) for v in obj]

        return _safe(obj)