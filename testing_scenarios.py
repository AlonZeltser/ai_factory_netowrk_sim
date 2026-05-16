"""Compatibility wrapper for the moved network test entrypoint."""
import random
import sys
from apps.network_sim import main
if __name__ == "__main__":
    random.seed(1972)
    raise SystemExit(main(sys.argv[1:]))
