"""PyInstaller entry script: the frozen EVLab executable."""

import multiprocessing
import sys

from evlab.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # the optimisation's spawn pool re-launches this executable
    sys.exit(main())
