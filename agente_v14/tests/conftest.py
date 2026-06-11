"""
Conftest for agente_v14 tests.
Adds parent directory to sys.path so modules can be imported.
"""
import sys
import os

# Add the parent directory (agente_v14/) to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
