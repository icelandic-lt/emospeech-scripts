#!/usr/bin/env python3
"""
Command-line compatible wrapper for Revoxx.
This maintains backward compatibility with the original rec.py arguments.
"""

import sys
import os

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from revoxx import main

if __name__ == '__main__':
    main()