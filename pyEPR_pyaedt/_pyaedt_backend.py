# This file is part of pyEPR: Energy participation ratio (EPR) design of
# quantum circuits in python.
"""
pyEPR._pyaedt_backend
=====================

PyAEDT connection backend for pyEPR.

This module is the **single place** in pyEPR that imports
``ansys.aedt.core`` (PyAEDT).  Everything PyAEDT-specific is confined here so
that the rest of the package — and in particular ``solution_types`` and
``calcs/`` — never pulls PyAEDT (or any Windows-only dependency) into its
import graph.  ``pyEPR_pyaedt.ansys`` imports *names* from here but the heavy PyAEDT
import is deferred until a connection is actually attempted.

Why PyAEDT
----------
pyEPR historically bootstrapped its connection with a raw ``win32com``
``Dispatch`` call, which is Windows-only and brittle across AEDT releases.
PyAEDT (``ansys-aedt-core``) owns session launch/attach, version detection,
gRPC transport (Linux), and clean release.  pyEPR lets PyAEDT manage the
**Desktop/session lifecycle** and then drives the *native* AEDT object tree
that PyAEDT exposes (``desktop.odesktop`` and below).

Important compatibility note (AEDT 2025 R2)
-------------------------------------------
On Windows with AEDT <= 2026 R1, PyAEDT still uses the COM backend under the
hood, so ``desktop.odesktop`` and its descendants are ordinary win32com
objects — identical to what pyEPR used before.  Only above 2026 R1 (or when
``settings.use_grpc_api`` is forced on, e.g. on Linux) do these become gRPC
wrapper objects.  Either way the string-based AEDT scripting API
(``GetModule``, ``GetSolutionType``, ``ExportEigenmodes``, the FieldsReporter
calculator methods, ...) is the same, which is what makes pyEPR's existing
wrapper layer port unchanged.
"""

from __future__ import annotations

import os

from . import logger

# ---------------------------------------------------------------------------
# Guarded PyAEDT import
# ---------------------------------------------------------------------------
# Mirror the win32com handling in ansys.py: importing pyEPR must never fail
# just because PyAEDT is absent (the no-HFSS analysis path, the calcs/ and
# solution_types modules, and downstream quantum-metal all import pyEPR_pyaedt on
# machines without AEDT).  The import is therefore attempted lazily and any
# failure is recorded, surfacing only when a connection is requested.

PYAEDT_INSTALL_HINT = (
    "PyAEDT is required to connect to Ansys AEDT/HFSS.\n"
    "    Install it with:  pip install ansys-aedt-core\n"
    "    (or:  pip install pyEPR-pyaedt[aedt])"
)

_pyaedt = None
_pyaedt_import_error = None


def _import_pyaedt():
    """Import and cache the ``ansys.aedt.core`` module.

    Returns
    -------
    module
        The imported ``ansys.aedt.core`` package.

    Raises
    ------
    ImportError
        If PyAEDT is not installed, with an actionable install hint.
    """
    global _pyaedt, _pyaedt_import_error
    if _pyaedt is not None:
        return _pyaedt
    try:
        import ansys.aedt.core as pyaedt  # noqa: PLC0415  (intentional lazy import)

        _pyaedt = pyaedt
        return _pyaedt
    except (ImportError, ModuleNotFoundError) as exc:
        # Fall back to the legacy top-level `pyaedt` distribution. Recent pyaedt
        # (1.x) re-exports `ansys.aedt.core`, so `Desktop`/`Hfss`/`Q3d` and the
        # current kwargs are still available.
        try:
            import pyaedt  # noqa: PLC0415

            _pyaedt = pyaedt
            return _pyaedt
        except (ImportError, ModuleNotFoundError) as exc2:  # pragma: no cover - env-dependent
            _pyaedt_import_error = exc2
            raise ImportError(
                f"{PYAEDT_INSTALL_HINT}\n    Original error: {exc2}"
            ) from exc2


def is_pyaedt_available() -> bool:
    """Return ``True`` if PyAEDT can be imported in this environment."""
    if _pyaedt is not None:
        return True
    try:
        _import_pyaedt()
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Desktop connection / lifecycle
# ---------------------------------------------------------------------------

def connect_desktop(
    version: str = None,
    non_graphical: bool = False,
    new_desktop: bool = False,
    port: int = 0,
    machine: str = "",
    aedt_process_id: int = None,
    use_grpc: bool = None,
):
    """Launch or attach to an AEDT Desktop session via PyAEDT.

    By default this **attaches to an already-running** AEDT session
    (``new_desktop=False``), matching pyEPR's historical behaviour of
    dispatching to the live application.  Set ``new_desktop=True`` to launch a
    fresh (optionally headless) session.

    Parameters
    ----------
    version : str, optional
        AEDT version string, e.g. ``"2025.2"`` for 2025 R2.  ``None`` lets
        PyAEDT pick the latest installed version.
    non_graphical : bool
        If ``True``, run AEDT without its GUI (batch / headless).
    new_desktop : bool
        If ``True``, start a new AEDT process; if ``False`` (default), attach
        to a running one.
    port : int
        gRPC port to connect to (remote/headless sessions).  ``0`` = ignore.
    machine : str
        Remote machine name for a gRPC session.  Empty = local.
    aedt_process_id : int, optional
        PID of a specific running AEDT process to attach to
        (only honoured when ``new_desktop=False``).
    use_grpc : bool, optional
        Force the gRPC transport on/off.  ``None`` keeps PyAEDT's default
        (COM on Windows for AEDT <= 2026 R1; gRPC above).  Set ``True`` on
        Linux.

    Returns
    -------
    ansys.aedt.core.Desktop
        The connected PyAEDT ``Desktop`` object.  ``desktop.odesktop`` exposes
        the native AEDT desktop object that pyEPR's wrappers drive.
    """
    pyaedt = _import_pyaedt()

    if use_grpc is not None:
        # settings is a process-wide singleton; only touch it when asked.
        try:
            from ansys.aedt.core.generic.settings import settings

            settings.use_grpc_api = bool(use_grpc)
        except Exception as exc:  # pragma: no cover - version-dependent
            logger.warning("Could not set PyAEDT use_grpc_api: %s", exc)

    logger.info(
        "Connecting to AEDT via PyAEDT (version=%s, new_desktop=%s, non_graphical=%s)...",
        version,
        new_desktop,
        non_graphical,
    )

    kwargs = dict(
        version=version,
        non_graphical=non_graphical,
        new_desktop=new_desktop,
        close_on_exit=False,  # never kill the user's session when pyEPR exits
    )
    # Only pass remote/PID knobs when meaningful; older PyAEDT releases are
    # picky about ``machine=""`` vs ``machine=None``.
    if port:
        kwargs["port"] = port
    if machine:
        kwargs["machine"] = machine
    if aedt_process_id is not None and not new_desktop:
        kwargs["aedt_process_id"] = aedt_process_id

    desktop = pyaedt.Desktop(**kwargs)
    logger.info("\tConnected to AEDT Desktop v%s", normalized_version(desktop))
    return desktop


def get_odesktop(desktop):
    """Return the native AEDT desktop object from a PyAEDT ``Desktop``."""
    return desktop.odesktop


def normalized_version(desktop) -> str:
    """Return the AEDT version as a ``"YYYY.N"`` string (e.g. ``"2025.2"``).

    pyEPR gates version-specific behaviour with simple ``>=`` string
    comparisons (e.g. ``self._ansys_version >= "2024.1"``), which this format
    supports directly.  Falls back to slicing the raw ``GetVersion()`` output
    if PyAEDT's normalized property is unavailable.
    """
    # PyAEDT 1.x exposes ``aedt_version_id`` -> "2025.2".
    ver = getattr(desktop, "aedt_version_id", None)
    if ver:
        return str(ver)
    try:
        # Raw GetVersion() returns e.g. "2025.2.0" + build; first 6 chars are
        # "YYYY.N" which is what pyEPR's comparisons expect.
        return str(get_odesktop(desktop).GetVersion())[0:6]
    except Exception:  # pragma: no cover - defensive
        return ""


def release_desktop(desktop, close_projects: bool = False, close_on_exit: bool = False) -> bool:
    """Detach from AEDT without (by default) closing projects or the session.

    Parameters
    ----------
    desktop : ansys.aedt.core.Desktop
        The PyAEDT desktop to release.
    close_projects : bool
        If ``True``, close open projects first.  Default ``False``.
    close_on_exit : bool
        If ``True``, terminate the AEDT process.  Default ``False`` so the
        user's interactive session keeps running.

    Returns
    -------
    bool
        Whatever PyAEDT's ``release_desktop`` returns, or ``False`` on error.
    """
    if desktop is None:
        return False
    try:
        return bool(
            desktop.release_desktop(close_projects=close_projects, close_on_exit=close_on_exit)
        )
    except Exception as exc:  # pragma: no cover - depends on live session
        logger.warning("Error releasing AEDT desktop: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Design-level application objects (full PyAEDT high-level API)
# ---------------------------------------------------------------------------

def open_design_app(project_name: str = None, design_name: str = None,
                    solution_type: str = None):
    """Attach a PyAEDT application object to a design in the running session.

    Returns a PyAEDT ``Hfss`` (or ``Q3d`` for Q3D designs) bound to the given
    project/design, attaching to the already-running AEDT session.  This gives
    pyEPR access to the full PyAEDT high-level API (modeler, setups, post,
    ``variable_manager``, ...) on the very design it is analysing.

    Parameters
    ----------
    project_name, design_name : str, optional
        Project/design to bind to.  ``None`` uses the active one.
    solution_type : str, optional
        pyEPR canonical solution type; ``"Q3D"`` selects a ``Q3d`` app, anything
        else selects ``Hfss``.

    Returns
    -------
    pyaedt application object (``Hfss`` or ``Q3d``)
    """
    pyaedt = _import_pyaedt()
    kwargs = dict(new_desktop=False, close_on_exit=False)
    if project_name:
        kwargs["project"] = project_name
    if design_name:
        kwargs["design"] = design_name
    if "q3d" in (solution_type or "").lower():
        return pyaedt.Q3d(**kwargs)
    return pyaedt.Hfss(**kwargs)


# ---------------------------------------------------------------------------
# Remote / gRPC file retrieval
# ---------------------------------------------------------------------------

def is_remote_session() -> bool:
    """Return ``True`` if connected to a *remote* gRPC AEDT session.

    Local sessions (COM, or local gRPC on the same machine) return ``False`` —
    there, ``Export*`` files land on the local filesystem and need no download.
    """
    try:
        from ansys.aedt.core.generic.settings import settings

        return bool(getattr(settings, "remote_rpc_session", None))
    except Exception:  # pragma: no cover - depends on PyAEDT internals
        return False


def download_if_remote(remote_path: str, overwrite: bool = True) -> str:
    """Download a server-side export file to the client when running remotely.

    Under a remote gRPC session, AEDT ``Export*`` calls write to the **server**
    filesystem; the returned path is therefore not directly readable on the
    client.  This helper downloads it and returns a local path.  When the
    session is local (the common Windows/COM case, including AEDT 2025 R2), it
    is a no-op and returns ``remote_path`` unchanged.

    Parameters
    ----------
    remote_path : str
        Path produced by an ``Export*`` call (server path under remote gRPC).
    overwrite : bool
        Overwrite an existing local copy.

    Returns
    -------
    str
        A path readable on the client.
    """
    try:
        from ansys.aedt.core.generic.settings import settings

        if not getattr(settings, "remote_rpc_session", None):
            return remote_path
        from ansys.aedt.core.generic.file_utils import check_and_download_file

        local = check_and_download_file(remote_path, overwrite=overwrite)
        return local or remote_path
    except Exception as exc:  # pragma: no cover - remote-only path
        logger.warning("download_if_remote: falling back to %s (%s)", remote_path, exc)
        return remote_path


def server_export_path(app, filename: str) -> str:
    """Return a server-writable path for an ``Export*`` call.

    Prefers PyAEDT's ``working_directory`` (created on the server under remote
    gRPC); falls back to the system temp dir for purely local sessions.

    Parameters
    ----------
    app : pyaedt application object, optional
        A PyAEDT ``Hfss``/``Q3d`` (or any object exposing ``working_directory``).
        May be ``None`` for local-only use.
    filename : str
        Base file name to place in the export directory.

    Returns
    -------
    str
        A path suitable as the destination of an AEDT ``Export*`` call.
    """
    workdir = getattr(app, "working_directory", None) if app is not None else None
    if workdir:
        try:
            return os.path.join(workdir, filename)
        except Exception:  # pragma: no cover - defensive
            pass
    import tempfile

    return os.path.join(tempfile.gettempdir(), filename)
