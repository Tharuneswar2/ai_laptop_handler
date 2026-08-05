"""Allow ``python -m pet`` to launch the pet engine directly."""

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
