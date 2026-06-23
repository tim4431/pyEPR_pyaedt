"""
CI-safe tests for the PyAEDT design-app exposure (Phase 3) and the remote-safe
file-export helper (Phase 4). No live AEDT — and no PyAEDT install — required;
PyAEDT is faked / monkeypatched.
"""
import os
import types


class _FakeApp:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeHfss(_FakeApp):
    pass


class _FakeQ3d(_FakeApp):
    pass


def test_open_design_app_selects_q3d_for_q3d(monkeypatch):
    from pyEPR_pyaedt import _pyaedt_backend as backend

    monkeypatch.setattr(
        backend, "_pyaedt", types.SimpleNamespace(Hfss=_FakeHfss, Q3d=_FakeQ3d)
    )
    app = backend.open_design_app("proj", "des", "Q3D")
    assert isinstance(app, _FakeQ3d)
    assert app.kwargs["project"] == "proj"
    assert app.kwargs["design"] == "des"
    # Attach to the running session; never close it.
    assert app.kwargs["new_desktop"] is False
    assert app.kwargs["close_on_exit"] is False


def test_open_design_app_selects_hfss_for_hfss_solution_types(monkeypatch):
    from pyEPR_pyaedt import _pyaedt_backend as backend

    monkeypatch.setattr(
        backend, "_pyaedt", types.SimpleNamespace(Hfss=_FakeHfss, Q3d=_FakeQ3d)
    )
    assert isinstance(backend.open_design_app("p", "d", "Eigenmode"), _FakeHfss)
    assert isinstance(backend.open_design_app("p", "d", "DrivenModal"), _FakeHfss)
    assert isinstance(backend.open_design_app("p", "d", None), _FakeHfss)


def test_is_remote_session_is_false_locally():
    from pyEPR_pyaedt import _pyaedt_backend as backend

    # A plain unit-test process has no remote RPC session.
    assert backend.is_remote_session() is False


def test_remote_safe_export_local_uses_tempfile(monkeypatch):
    from pyEPR_pyaedt import ansys

    # Local session: behaviour must match the old plain `tempfile.mktemp()`.
    monkeypatch.setattr(ansys, "_is_remote_session", lambda: False)

    captured = {}
    out = ansys._remote_safe_export(
        None, lambda p: captured.__setitem__("p", p), suffix=".txt"
    )
    assert out == captured["p"]
    assert out.endswith(".txt")


def test_remote_safe_export_remote_uses_workdir_and_downloads(monkeypatch, tmp_path):
    from pyEPR_pyaedt import ansys

    # Remote session: export into the server-side working_directory, then download.
    monkeypatch.setattr(ansys, "_is_remote_session", lambda: True)
    downloaded = {}
    monkeypatch.setattr(
        ansys,
        "_download_if_remote",
        lambda p: (downloaded.__setitem__("p", p), p)[1],
    )

    design = types.SimpleNamespace(working_directory=str(tmp_path))
    captured = {}
    out = ansys._remote_safe_export(
        design, lambda p: captured.__setitem__("p", p), suffix=".conv"
    )
    assert os.path.dirname(captured["p"]) == str(tmp_path)
    assert captured["p"].endswith(".conv")
    assert downloaded["p"] == captured["p"]   # the export was downloaded
    assert out == captured["p"]
