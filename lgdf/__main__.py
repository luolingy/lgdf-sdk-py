"""支持 `python -m lgdf ...`。"""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
