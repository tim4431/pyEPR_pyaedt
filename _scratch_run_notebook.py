"""Throwaway runner: execute a tutorial notebook in place, keep partial outputs on failure.

Usage: python _scratch_run_notebook.py <notebook-filename-in-_tutorial_notebooks_pyaedt>
"""
import sys
import traceback
from pathlib import Path

import nbformat
from nbclient import NotebookClient

NBDIR = Path(r"c:\Code\pyEPR_pyaedt\_tutorial_notebooks_pyaedt")
PATH = NBDIR / sys.argv[1]

nb = nbformat.read(PATH, as_version=4)
client = NotebookClient(
    nb,
    timeout=3600,
    kernel_name="python3",
    resources={"metadata": {"path": str(NBDIR)}},
)
try:
    client.execute()
    print("NOTEBOOK-RUN: OK")
except Exception:
    traceback.print_exc()
    print("NOTEBOOK-RUN: FAILED")
finally:
    nbformat.write(nb, PATH)
    print("NOTEBOOK-RUN: outputs written")
