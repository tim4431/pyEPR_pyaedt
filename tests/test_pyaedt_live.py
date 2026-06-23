"""
Live AEDT smoke tests — require a running Ansys session with an active project
and design.  Marked ``@pytest.mark.hfss`` so CI skips them.

Run locally against your open AEDT 2025.2 session with:

    pytest -m hfss tests/test_pyaedt_live.py -v
"""
import pytest


@pytest.mark.hfss
def test_pyaedt_app_exposed_on_active_connection():
    """`pinfo.pyaedt` returns a live PyAEDT app bound to the connected design."""
    import pyEPR_pyaedt as epr

    try:
        pinfo = epr.ProjectInfo()  # attach to the active project/design/setup
    except Exception as e:
        pytest.skip(f"Cannot connect to AEDT: {e}")

    try:
        assert pinfo.design is not None, "no active design to bind to"

        app = pinfo.pyaedt
        assert app is not None, "PyAEDT app was not attached to the design"

        # It is a real PyAEDT application exposing the full high-level API on
        # the same design pyEPR is connected to.
        assert hasattr(app, "odesign")
        assert hasattr(app, "variable_manager")
        assert hasattr(app, "modeler")

        # Same object via the design wrapper.
        assert pinfo.design.pyaedt_app is app
    finally:
        try:
            if getattr(pinfo, "app", None) is not None:
                # Detach but leave the user's AEDT session and project running.
                pinfo.app.release_desktop(close_projects=False, close_on_exit=False)
        except Exception:
            pass
