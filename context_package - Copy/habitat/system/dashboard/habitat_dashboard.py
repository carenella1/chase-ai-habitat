import json
from pathlib import Path


class HabitatDashboard:

    def __init__(self, monitor, telemetry, memory_lifecycle, research_manager, evolution):

        self.monitor = monitor
        self.telemetry = telemetry
        self.memory_lifecycle = memory_lifecycle
        self.research_manager = research_manager
        self.evolution = evolution

    def system_overview(self):

        return {
            "system": self.monitor.snapshot(),
            "memory": self.memory_lifecycle.memory_summary(),
            "research_programs": len(self.research_manager.programs),
            "evolution_queue": len(self.evolution.get_active_proposals()),
            "recent_activity": self.telemetry.recent_events()
        }

    def research_overview(self):

        return self.research_manager.programs

    def evolution_overview(self):

        return self.evolution.get_active_proposals()

    def export_snapshot(self):

        snapshot = self.system_overview()

        Path("data/system").mkdir(parents=True, exist_ok=True)

        with open("data/system/dashboard_snapshot.json", "w") as f:
            json.dump(snapshot, f, indent=2)

        return snapshot