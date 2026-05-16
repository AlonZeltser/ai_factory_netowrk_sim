"""Compatibility wrapper for the moved AI-factory entrypoint."""
import sys
from apps.ai_factory_sim import main
if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
