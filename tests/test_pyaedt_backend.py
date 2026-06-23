"""
CI-safe tests for the PyAEDT connection backend and the field-calculator
translation.

None of these tests require a live Ansys/AEDT session or even PyAEDT to be
installed:

* Import-isolation tests run in a subprocess with all Windows/AEDT packages
  blocked, proving the no-HFSS analysis path (and downstream quantum-metal on
  Linux) imports cleanly.
* Connection-routing tests inject a *fake* ``ansys.aedt.core`` so we can assert
  pyEPR attaches to a running session by default and reads the normalized
  version, without launching anything.
* The CalcObject contract test records the native FieldsReporter calls a field
  expression emits, pinning the translation so it cannot silently drift across
  the COM and gRPC backends.

Live HFSS tests live elsewhere and are marked ``@pytest.mark.hfss``.
"""
import subprocess
import sys
import types

import pytest


# ---------------------------------------------------------------------------
# Import isolation — the no-HFSS path must import with no AEDT/Windows deps
# ---------------------------------------------------------------------------

_BLOCK_AND_IMPORT = r"""
import sys

_BLOCKED = {"win32com", "ansys", "pyaedt", "pythoncom", "pywintypes"}

class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in _BLOCKED:
            raise ImportError("blocked for test: " + name)
        return None

sys.meta_path.insert(0, _Blocker())

import pyEPR                      # full package init
import pyEPR.solution_types       # must stay COM/pyaedt free
import pyEPR.calcs                # must stay COM/pyaedt free
import pyEPR.ansys                # must still import (connection guarded/lazy)

# None of the blocked packages should have been imported as a side effect.
for _m in ("win32com", "ansys.aedt.core", "pyaedt", "pythoncom"):
    assert _m not in sys.modules, "unexpected import: " + _m

print("ISOLATION_OK")
"""


def test_no_hfss_import_path_is_clean():
    """pyEPR, solution_types, calcs and ansys import with all AEDT deps blocked."""
    result = subprocess.run(
        [sys.executable, "-c", _BLOCK_AND_IMPORT],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Isolated import failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "ISOLATION_OK" in result.stdout


def test_ansys_module_exposes_public_surface():
    """The rewritten ansys.py still exports the names consumers rely on."""
    from pyEPR import ansys

    for name in (
        "HfssApp",
        "HfssDesktop",
        "HfssProject",
        "HfssDesign",
        "HfssEMSetup",
        "HfssFieldsCalc",
        "CalcObject",
        "NamedCalcObject",
        "load_ansys_project",
        "get_active_project",
    ):
        assert hasattr(ansys, name), f"ansys.{name} missing after rewrite"


# ---------------------------------------------------------------------------
# Backend behaviour without PyAEDT installed
# ---------------------------------------------------------------------------

def test_connect_raises_actionable_error_without_pyaedt():
    from pyEPR import _pyaedt_backend as backend

    if backend.is_pyaedt_available():
        pytest.skip("PyAEDT is installed in this environment; skipping missing-dep test")

    with pytest.raises(ImportError) as excinfo:
        backend.connect_desktop()
    assert "ansys-aedt-core" in str(excinfo.value)


def test_download_if_remote_is_noop_when_local():
    from pyEPR import _pyaedt_backend as backend

    # With no remote gRPC session (or no PyAEDT at all) the path is unchanged.
    p = r"C:\some\export\eigenmodes.csv"
    assert backend.download_if_remote(p) == p


def test_server_export_path_prefers_working_directory(tmp_path):
    import os

    from pyEPR import _pyaedt_backend as backend

    app = types.SimpleNamespace(working_directory=str(tmp_path))
    out = backend.server_export_path(app, "eigenmodes.csv")
    assert os.path.dirname(out) == str(tmp_path)
    assert out.endswith("eigenmodes.csv")

    # Falls back to a temp dir when no app/working_directory is available.
    out2 = backend.server_export_path(None, "eigenmodes.csv")
    assert out2.endswith("eigenmodes.csv")


# ---------------------------------------------------------------------------
# Connection routing with a fake PyAEDT (no AEDT launched)
# ---------------------------------------------------------------------------

class _FakeODesktop:
    """Stand-in for the native AEDT desktop object exposed by PyAEDT."""

    def GetVersion(self):  # noqa: N802 - mirror AEDT COM API name
        return "2025.2.0"


class _FakeDesktop:
    """Stand-in for ``ansys.aedt.core.Desktop``; records constructor kwargs."""

    last_kwargs = None
    aedt_version_id = "2025.2"

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs
        self.odesktop = _FakeODesktop()
        self.released_with = None

    def release_desktop(self, close_projects=True, close_on_exit=True):  # noqa: N802
        self.released_with = (close_projects, close_on_exit)
        return True


@pytest.fixture
def fake_pyaedt(monkeypatch):
    """Inject a fake ``ansys.aedt.core`` module into the backend's import cache."""
    from pyEPR import _pyaedt_backend as backend

    fake_module = types.SimpleNamespace(Desktop=_FakeDesktop)
    monkeypatch.setattr(backend, "_pyaedt", fake_module)
    _FakeDesktop.last_kwargs = None
    return backend


def test_connect_desktop_attaches_to_running_session_by_default(fake_pyaedt):
    backend = fake_pyaedt

    desktop = backend.connect_desktop()

    kwargs = _FakeDesktop.last_kwargs
    # Attach to a running session and never kill it when pyEPR exits.
    assert kwargs["new_desktop"] is False
    assert kwargs["close_on_exit"] is False
    # Version is normalized to the "YYYY.N" form pyEPR's >= comparisons expect.
    assert backend.normalized_version(desktop) == "2025.2"


def test_connect_desktop_passes_launch_options(fake_pyaedt):
    backend = fake_pyaedt

    backend.connect_desktop(version="2025.2", non_graphical=True, new_desktop=True)

    kwargs = _FakeDesktop.last_kwargs
    assert kwargs["version"] == "2025.2"
    assert kwargs["non_graphical"] is True
    assert kwargs["new_desktop"] is True


def test_hfssapp_builds_desktop_from_pyaedt(fake_pyaedt):
    from pyEPR import ansys

    app = ansys.HfssApp()
    desktop = app.get_app_desktop()

    assert isinstance(desktop, ansys.HfssDesktop)
    # Native handle is the fake odesktop, and version came from PyAEDT.
    assert desktop.version == "2025.2"
    assert desktop._desktop.GetVersion() == "2025.2.0"

    # release_desktop forwards "leave it running" defaults.
    app.release_desktop()
    assert app._desktop_app.released_with == (False, False)


# ---------------------------------------------------------------------------
# Field-calculator translation contract (backend-agnostic)
# ---------------------------------------------------------------------------

class _RecordingFieldsModule:
    """Fake FieldsReporter module that records every native call it receives."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _method(*args):
            self.calls.append((name, args))
            if name == "GetTopEntryValue":
                return [42.0]
            return None

        return _method


class _FakeSetup:
    """Minimal stand-in for an HfssSetup as seen by CalcObject."""

    def __init__(self, fields_module):
        self.parent = types.SimpleNamespace(_fields_calc=fields_module)
        self.solution_name = "Setup1 : LastAdaptive"


def test_calcobject_emits_expected_fields_calculator_stack():
    """A field expression must replay as a precise native FieldsReporter sequence.

    This is the regression oracle for the field-calculator translation: it holds
    identically whether the underlying module is win32com (Windows/COM) or a gRPC
    wrapper (Linux), because both are driven through the same string API.
    """
    from pyEPR import ansys

    recorder = _RecordingFieldsModule()
    setup = _FakeSetup(recorder)
    fields = ansys.HfssFieldsCalc(setup)

    # Electric energy density integrated over a volume — a real pyEPR pattern.
    value = fields.Vector_E.times_eps().integrate_vol("AllObjects").evaluate(phase=0)

    assert value == 42.0

    op_names = [name for name, _ in recorder.calls]
    assert op_names == [
        "CopyNamedExprToStack",  # Vector_E named expression
        "ClcMaterial",           # times_eps()
        "EnterVol",              # integrate_vol(...)
        "CalcOp",                # Integrate
        "ClcEval",               # evaluate()
        "GetTopEntryValue",      # evaluate() result read-back
    ]
    assert recorder.calls[0] == ("CopyNamedExprToStack", ("Vector_E",))
    assert recorder.calls[2] == ("EnterVol", ("AllObjects",))
    assert recorder.calls[3] == ("CalcOp", ("Integrate",))
    # times_eps() multiplies by permittivity via the material operation.
    assert recorder.calls[1][0] == "ClcMaterial"
    assert "Permittivity (epsi)" in recorder.calls[1][1]
