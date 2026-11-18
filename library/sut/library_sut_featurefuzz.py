"""Start the FeatureFuzz-inspired Library SUT on port 23602 by default."""

from pathlib import Path
from runpy import run_path


if __name__ == "__main__":
    server = Path(__file__).resolve().parents[1] / "feature-mutants-v001" / "server.py"
    run_path(str(server))["main"](default_port=23602)
