"""Start the literature-based Library SUT v003 from the shared SUT directory."""

from pathlib import Path
from runpy import run_path


if __name__ == "__main__":
    run_path(str(Path(__file__).resolve().parents[1] / "mutants-v003" / "mutants.py"),
             run_name="__main__")
