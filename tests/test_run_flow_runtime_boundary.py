from __future__ import annotations

from pathlib import Path
import unittest


class RunFlowRuntimeBoundaryTests(unittest.TestCase):
    def test_run_flow_routes_agent_steps_through_host_runtime(self) -> None:
        source = Path(__file__).parents[1].joinpath("src", "run_flow.py").read_text(encoding="utf-8")

        self.assertIn("_host_agent_runtime", source)
        self.assertIn("fusion_flow.adapters.psi_runtime", source)
        self.assertNotIn("from psi_agent", source)


if __name__ == "__main__":
    unittest.main()
