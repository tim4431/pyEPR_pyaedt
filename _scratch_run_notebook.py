"""Throwaway runner: execute Tutorial 1 in place, keeping partial outputs on failure."""
import traceback

import nbformat
from nbclient import NotebookClient

PATH = r"c:\Code\pyEPR_pyaedt\_tutorial_notebooks_pyaedt\Tutorial 1.  Startup example.ipynb"

nb = nbformat.read(PATH, as_version=4)
client = NotebookClient(
    nb,
    timeout=3600,
    kernel_name="python3",
    resources={"metadata": {"path": r"c:\Code\pyEPR_pyaedt\_tutorial_notebooks_pyaedt"}},
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
