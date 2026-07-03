# PyAEDT Compatibility — Implementation Plan

**Status:** In progress — **Phase 1 (connection layer) implemented & green**
**Author:** drafted by Claude Code, 2026-06-22
**Scope:** Make pyEPR able to drive Ansys AEDT through **PyAEDT**
(`ansys-aedt-core`, importable as `ansys.aedt.core`; legacy package name
`pyaedt`) instead of *only* raw `win32com` COM — unlocking Linux/macOS via
gRPC and offloading AEDT version churn to PyAEDT, **without breaking the
existing public API or numerical results**.

---

## 0. Decision & status (2026-06-22)

**Maintainer decision:** go with a **full rewrite onto PyAEDT** (not the
optional dual-backend adapter), targeting **AEDT 2025 R2** (`"2025.2"`).

**What "full rewrite" means in practice, and why.** PyAEDT *is* COM under the
hood on Windows for AEDT ≤ 2026 R1 — it exposes the same native object tree
(`odesktop`/`oproject`/`odesign`/`ofieldsreporter`/…) that pyEPR already drives,
and PyAEDT's own high-level helpers call those very objects. So the rewrite
replaces pyEPR's **connection / session / version / lifecycle** layer wholesale
with PyAEDT, and keeps the field-calculator engine and geometry calls running on
the native handles PyAEDT hands us (there is no higher-level PyAEDT API that
computes pyEPR's specific field integrals). Rewriting the 100+ `HfssModeler`
geometry methods to PyAEDT's modeler API is **not** required for "compatible
with PyAEDT" and is deferred (it's not on the EPR analysis path).

**Validated against the maintainer's actual install:** PyAEDT **0.26.1**,
conda env `hfss`. Every API this rewrite uses was confirmed present:
`Desktop(version, non_graphical, new_desktop, close_on_exit, machine, port,
aedt_process_id)`, `Desktop.aedt_version_id`, and on the app object
`odesktop/oproject/odesign/osolution/ofieldsreporter/oboundary/oanalysis/
working_directory/aedt_version_id`, plus `settings.use_grpc_api` and
`check_and_download_file`.

| Phase | Scope | Status |
|---|---|---|
| **1. Connection layer** | PyAEDT owns Desktop launch/attach, version, release; win32com no longer needed to connect; import-safe (guarded/lazy); CI-safe tests | ✅ **Done + live-validated** |
| **2. Live validation** | Attach to running 2025.2, read project/design/setup | ✅ **Done** — connected to a live 2025.2 **gRPC** session (port 50051), Q3D design, via `epr.ProjectInfo()` |
| **3. PyAEDT-native layer** | Expose the live PyAEDT `Hfss`/`Q3d` app on the connection: `pinfo.pyaedt` / `design.pyaedt_app` (lazy, best-effort) → full PyAEDT high-level API on the connected design | ✅ **Done (app exposure)**. Method-by-method conversion of variable *writes* / setup creation / eigenmode solve is **deferred** — validation-gated (won't replace working code with calls untestable off a live session) |
| **4. gRPC/remote-safe exports** | `_remote_safe_export()` helper: **local path == old `tempfile` behaviour**, remote writes to `working_directory` + downloads. Wired: **eigenmodes + Q3D matrix + convergence/mesh/profile** | ✅ Key sites done. Remaining (network/report CSV) follow the identical one-line pattern; they already work on local/COM sessions |
| **5. Q3D + modeler** | Q3D matrix export remote-safe; modeler reachable via `pinfo.pyaedt.modeler` | ✅ Q3D export done; modeler via app exposure. Porting `HfssModeler` wholesale to PyAEDT's modeler API still optional/deferred |

**Note:** the package was renamed `pyEPR` → **`pyEPR_pyaedt`** (dist `pyEPR-pyaedt`)
during this work; `import pyEPR` no longer resolves.

**Files (Phases 1, 3, 4):** `pyEPR_pyaedt/_pyaedt_backend.py` (connect/version/release,
`open_design_app`, `is_remote_session`, export helpers), `pyEPR_pyaedt/ansys.py`
(PyAEDT bootstrap; `HfssDesign.pyaedt_app`/`working_directory`; `_remote_safe_export`;
eigenmode + Q3D-matrix wiring), `pyEPR_pyaedt/project_info.py` (`ProjectInfo.pyaedt`),
`pyEPR_pyaedt/__init__.py`, `pyproject.toml` (`[aedt]` extra), tests
(`test_pyaedt_backend.py`, `test_pyaedt_app.py`, `test_pyaedt_live.py`).
Branch: `claude/pyaedt-rewrite`. CI-safe suite: **182 pass / 1 skip**, `pylint -E` clean.

---

## Remaining work (actionable checklist)

Deferred deliberately — each is **validation-gated**: it would replace
live-validated native-COM code with PyAEDT calls that can't be tested off a
running AEDT session. The PyAEDT app is already exposed (`pinfo.pyaedt`), so
these are incremental, not blockers.

- [x] **Docs build** — ✅ zero-warning `sphinx -b html` (exit 0); the rename is
      docs-clean (all `pyEPR_pyaedt` autodoc/cross-refs resolve). Also fixed a
      pre-existing duplicate `exclude_patterns` bug in `conf.py` that had silently
      disabled the notebook/README excludes.
- [x] **Variables → PyAEDT** — ✅ done + **validated live on tutorial2**: `get_variable_value`
      11/11 identical to raw COM; `set_variable` create→read→delete round-trip; `set_variables`
      reuses the parser + validated set path; native fallback. (`fab8adc`)
- [x] **Q3D matrix pandas fix** — ✅ `delim_whitespace` (removed in pandas ≥2.2) → `sep=r"\s+"`.
      Phase-4 export wiring confirmed writing the file live; full parse not end-to-end validatable
      because tutorial2's Q3D exports **empty matrix sections** (no solved matrix). (`d490759`)
- [ ] **Setup creation → PyAEDT** — `create_q3d_setup` is validatable on tutorial2; `create_em_setup`
      / `create_dm_setup` / `create_dt_setup` need an HFSS design (see boundary below).
- [x] **Eigenmode read** — ✅ validated end-to-end on a solved eigenmode design
      (`single_transmon`): `eigenmodes()` returned `[4.289, 9.242] GHz` through the
      Phase-4 `ExportEigenmodes` wiring.
- [x] **Convergence/mesh/profile exports** — ✅ (2026-07-02) wired through
      `_remote_safe_export` **and fixed for AEDT 2025 R2**: the scripting API dropped the
      trailing `overwrite` argument from `ExportMeshStats`/`ExportConvergence`/`ExportProfile`
      (matching PyAEDT's 3-arg calls); we try the new signature first and fall back to the
      legacy one for older AEDT. Q3D overrides pass the `"CG"` data-block arg (per PyAEDT
      `q3d.py`). Under gRPC a no-solution export now *raises* (`GrpcApiError`) where COM wrote
      nothing — all three getters catch this and return `None` with a "design not solved?" log.
      Live-validated on 2025.2 gRPC (`single_transmon`, unsolved): convergence + profile export
      empty tables through the new signature; mesh stats degrade gracefully. **Mesh CSV parse
      (`skiprows=7`) still unvalidated against a solved 2025.2 design.**
- [ ] **Remaining export sites** — wire network data / report CSV
      through `_remote_safe_export` (same one-liner; already work on local/COM sessions).
- [ ] **Setup creation → PyAEDT** — `create_q3d_setup` / `create_em_setup` / etc. via
      `pyaedt_app.create_setup` (still native; works).

> **✅ Core EPR path validated end-to-end (2026-06-23).** After the maintainer solved an
> eigenmode `single_transmon` design, the **complete pyEPR pipeline ran through PyAEDT** and
> produced correct transmon physics: connection → eigenmodes `[4.289, 9.242] GHz` → field
> calculator (E/H energies; `U_E/(U_E+U_H)`=0.98 transmon mode, 0.50 distributed mode) →
> junction participation `p_0j=0.98` → `do_EPR_analysis` save → `QuantumAnalysis` (qutip) →
> **anharmonicity α≈177 MHz, cross-Kerr≈2.3 MHz, f_ND≈[4118, 9241] MHz**. Exercising the full
> pipeline surfaced and fixed **5 pre-existing dependency-compat bugs** (none from the rewrite):
> pandas `delim_whitespace` (Q3D reader), pint `ureg`-indexing ×4 (`_get_lv`/variation), the
> `pyaedt`-property pickle leak (`_Forbidden`), numpy `np.mat` (`print_matrix`), and a
> single-variation `IndexError` in `QuantumAnalysis`.
- [ ] **`HfssModeler`** — optional wholesale port to PyAEDT's modeler API (not on the
      EPR path; users can already reach it via `pinfo.pyaedt.modeler`).
- [ ] **Ecosystem docs** — reframe `.claude/commands/*` + `ecosystem.md` for the fork
      (they still reference the upstream `pyEPR-quantum` / quantum-metal relationship).

---

## TL;DR

- **The linchpin:** PyAEDT does not hide the native AEDT objects — it exposes
  them. `app.odesign`, `app.oproject`, `app.odesktop`, `app.osolution`, and
  crucially `app.odesign.GetModule("FieldsReporter")` / `GetModule("Solutions")`
  work *exactly* like today's COM handles. On Windows they wrap COM; on Linux
  they route through PyAEDT's gRPC plugin (`AedtObjWrapper`) with the same
  string-based method API.
- **Therefore this is an adapter/backend swap, not a rewrite.** pyEPR's
  `CalcObject` field-calculator stack — which only does
  `getattr(self.calc_module, fn)(arg)` — and nearly all `Analyze` /
  `ExportEigenmodes` / `GetNominalVariation` calls keep working *unchanged* if
  their underlying handle is sourced from a PyAEDT app instead of
  `win32com.Dispatch`.
- **Recommended approach:** introduce a pluggable connection **backend**
  (`"com"` = today, default; `"pyaedt"` = new) behind the *existing*
  `HfssApp/HfssDesktop/HfssProject/HfssDesign` wrapper classes. The wrappers
  already separate "native object" (`self._design`, `self.calc_module`, …) from
  pyEPR logic, so only *how those handles are obtained* changes.
- **The single biggest porting risk is not the API — it's files.** Six places
  use the `Export*` → `tempfile.mktemp()` → read-local-file pattern. Under gRPC
  the export lands on the **AEDT server's** filesystem, not the client's. This
  must be handled with PyAEDT's file-retrieval helpers.
- **De-risk first:** a 1–2 day proof-of-concept (connect via PyAEDT → run one
  eigenmode extraction through the *unchanged* wrappers → assert identical
  numbers) validates the whole strategy before any broad work.

---

## 1. Why (motivation & constraints)

What the EPR method actually needs from the EM simulator (per
[arXiv:2010.00620](https://arxiv.org/abs/2010.00620) and `core_distributed_analysis.py`):
an **eigenmode** simulation of the linearized circuit, then per-mode/per-junction
**field integrals** (E/H energies, surface/line integrals for currents &
voltages, dissipation integrals) plus eigenfrequencies and Q. All of this is
post-processing on a solved design — pyEPR is a *quantization/post-processing*
library, not a geometry tool (see `.claude/context/ecosystem.md`).

Motivations for PyAEDT compatibility:

1. **Cross-platform.** `win32com` is Windows-only. The theorist/student/no-HFSS
   audience and the quantum-metal automation path run on Linux/macOS. PyAEDT's
   gRPC transport makes the *HFSS-driving* path possible off Windows too.
2. **AEDT version churn.** Per `.claude/context/lessons-learned.md` and the
   ecosystem doc, version compatibility is the #1 user pain. PyAEDT tracks AEDT
   releases and absorbs signature/string changes — letting pyEPR stop chasing
   them by hand.
3. **Connection robustness.** PyAEDT has mature session attach/launch,
   non-graphical mode, and process management vs. pyEPR's hand-rolled
   `Dispatch` + "run as admin" bootstrap.

Hard constraints (from `CLAUDE.md` / context files) — these shape every choice:

- **Public API must stay stable.** `ProjectInfo` / `DistributedAnalysis` /
  `QuantumAnalysis` and the deprecated aliases (`Project_Info`,
  `pyEPR_HFSSAnalysis`, `pyEPR_Analysis`) are imported by **quantum-metal**.
  No signature breaks; additions only.
- **`solution_types.py` and `calcs/` must never import COM or any Windows-only
  lib.** They are imported by quantum-metal on Linux. PyAEDT must likewise stay
  out of those modules' import graph.
- **Windows-only / heavy deps stay confined to `ansys.py`** (and a new sibling
  backend module). `ansys-aedt-core` must be an **optional** dependency so the
  no-HFSS analysis path and quantum-metal imports never require it.
- **Numerical results must not regress.** `tests/correct_results.pkl` and
  `tests/data*.npz` are the oracle.

---

## 2. Current Ansys-interaction surface (what we're porting)

All COM lives in **`pyEPR_pyaedt/ansys.py`**; everything else is pure-Python and
delegates through wrapper objects. The Windows-only footprint is tiny and fully
localized:

| Windows-only call | `ansys.py` site | Note |
|---|---|---|
| `from win32com.client import CDispatch, Dispatch` | `:50` | sole import |
| `self._app = Dispatch(ProgID)` | `:381` | the *only* bootstrap |
| `pythoncom._GetInterfaceCount()` | `:263` | refcount debug |
| `isinstance(v, CDispatch)` | `:276` | `COMWrapper.release()` |
| `ctypes.windll.shell32.IsUserAnAdmin()` | `:3729` | `get_active_project()` |

**Wrapper hierarchy** (`HfssApp → HfssDesktop → HfssProject → HfssDesign →
HfssSetup{DM,DT,EM,Q3D} → …Solutions → CalcObject`). Each wrapper stores a
native handle and delegates attribute access to it via `COMWrapper`. The handles
are obtained from exactly three roots:

- `HfssApp.__init__`: `Dispatch(ProgID)` → `:381`
- `HfssApp.get_app_desktop`: `self._app.GetAppDesktop()` → `:384`
- `HfssDesign.__init__`: nine `design.GetModule(...)` + `SetActiveEditor("3D Modeler")` → `:722-730`

**Consumer surface that actually matters for EPR** (`core_distributed_analysis.py`):
`setup.get_fields()`, `setup.get_solutions()`, `solutions.eigenmodes(lv)`,
`design.set_variables()`, `design.Clear_Field_Clac_Stack()`,
`setup.get_mesh_stats()` / `get_convergence()`, and the `CalcObject` field
math (`Vector_E.times_eps().integrate_vol().evaluate(...)`, etc.).

**Field calculator (the trickiest piece, but self-contained):** `CalcObject`
builds an RPN `self.stack` of `(fn, arg)` tuples and, on `.evaluate()`, replays
them with `getattr(self.calc_module, fn)(arg)` then calls
`ClcEval` + `GetTopEntryValue` (`ansys.py:3661-3696`). `calc_module` is just
`design.GetModule("FieldsReporter")`. **Because PyAEDT exposes `GetModule`, this
entire mechanism ports for free** once `calc_module` comes from the PyAEDT
design object.

**The file-export pattern (the real risk):** six sites do
`fn = tempfile.mktemp(); o<X>.Export<Y>(..., fn); read(fn)`:

| Site | Export call | Reads |
|---|---|---|
| `ansys.py:1518` | `ExportConvergence` / mesh | `.conv` / `.mesh` |
| `ansys.py:1855` | `ExportEigenmodes` | eigenmode table |
| `ansys.py:1902` | (dead code) | — |
| `ansys.py:2063` | `ExportNetworkData` | S-params |
| `ansys.py:2131` | report → CSV | `.csv` |
| (Q3D) `ExportMatrixData` | matrix `.txt` | — |

Under COM (same machine) the file is local. Under gRPC the file is written on
the **server**; the client path from `tempfile.mktemp()` won't exist locally.

---

## 3. Recommended architecture — pluggable connection backend

Add a thin backend seam **underneath** the existing wrappers. Nothing above the
handle-acquisition layer changes.

```
ProjectInfo.connect(backend="com" | "pyaedt")
        │
        ▼
pyEPR_pyaedt/_ansys_backend.py   ← NEW; the only place that imports pyaedt
   ├─ ComBackend     : Dispatch(...)  → native desktop/project/design objects
   └─ PyAedtBackend  : ansys.aedt.core.Desktop/Hfss(...) → .odesktop/.oproject/.odesign
        │  returns native handles
        ▼
HfssApp / HfssDesktop / HfssProject / HfssDesign   ← UNCHANGED logic
   └─ CalcObject, …Solutions, HfssSetup            ← UNCHANGED logic
```

Key idea: a backend's job is to return **native AEDT objects** (the thing today
called `_wrapped_COM_object`). The wrappers don't care whether that object is a
`CDispatch` or a PyAEDT `AedtObjWrapper` — they only call AEDT methods on it.

### Why this over a full rewrite to idiomatic PyAEDT

| | Adapter/backend (recommended) | Full rewrite to PyAEDT high-level API |
|---|---|---|
| Public API stability | Preserved trivially | High risk of drift |
| Reuses validated field-calc/EPR math | Yes (unchanged) | Re-implement on `FieldsCalculator`/`post` |
| Effort / surface | Small, localized | Large (modeler is 100+ methods) |
| Numerical-regression risk | Low | High |
| Idiomatic / future-proof | Partial | Full |

Recommendation: **adapter now**, optionally migrate *individual* subsystems to
idiomatic PyAEDT later (new features only), never ripping out working code.

---

## 4. Phased implementation

### Phase 0 — Scaffolding & safety net (no behavior change)
- `pyproject.toml`: add optional extra
  `aedt = ["ansys-aedt-core>=0.9"]` (keep out of core `dependencies`).
- New module `pyEPR_pyaedt/_ansys_backend.py`; allow `ansys.aedt.core` import **only**
  here and in `ansys.py`. Add a lint/CI guard asserting no pyaedt/win32com
  import leaks into `solution_types.py` or `calcs/`.
- **CI-safe contract test for the field calculator:** feed `CalcObject` a *fake*
  module that records every `getattr(module, fn)(arg)` call, and assert the
  emitted call sequence for `calc_energy_electric/magnetic`, currents, voltage,
  dissipation matches a golden list. This pins the translation **without a
  license** and guards both backends forever.
- Add `@pytest.mark.hfss` end-to-end tests (connect → eigenmode → χ/freqs) as
  the regression oracle against `correct_results.pkl`.

### Phase 1 — Connection layer via PyAEDT
- Implement `PyAedtBackend`: attach to a running session or launch one via
  `ansys.aedt.core.Desktop(new_desktop=False, version=..., non_graphical=...,
  port=...)` (param names vary slightly by PyAEDT version — verify against the
  pinned floor), then expose `.odesktop`, `.oproject`, `.odesign`.
- Route `load_ansys_project(...)` and `ProjectInfo.connect_project/
  connect_design/connect_setup` through the backend via a new **keyword-only**
  `backend="com"` arg (default preserves today's behavior exactly).
- Guard the Windows-only bits so the `"pyaedt"` path never touches them:
  `pythoncom._GetInterfaceCount` (`:263`), `isinstance(v, CDispatch)` (`:276`),
  `IsUserAnAdmin` (`:3729`). Make `COMWrapper.release()` a no-op for non-COM
  handles.

### Phase 2 — Field calculator & solutions over the backend
- Confirm `HfssDesign.__init__`'s nine `GetModule(...)` calls + `SetActiveEditor`
  resolve on the PyAEDT design object (`odesign.GetModule(...)` is confirmed to
  work; verify `SetActiveEditor("3D Modeler")` under gRPC).
- Validate `CalcObject.evaluate` → `ClcEval`/`GetTopEntryValue` returns the same
  float through the pyaedt handle.
- **Fix the export-to-file pattern (the big one).** Introduce one helper, e.g.
  `backend.retrieve_export(remote_or_local_path)`, that is a passthrough under
  COM and uses PyAEDT's server→client download (e.g. `app.working_directory` /
  PyAEDT's file-transfer helpers) under gRPC. Route all six sites
  (`:1518, :1855, :2063, :2131`, Q3D matrix, + delete dead `:1902`) through it.
  Prefer writing exports into PyAEDT's managed results dir rather than a raw
  `tempfile.mktemp()`.

### Phase 3 — Version handling consolidation
- Keep `solution_types.normalize()` and the **AEDT 2024.1 hybrid `SetSolutionType`
  fix** (`new_dm_design`/`new_dt_design`) — still required; verify whether
  PyAEDT's `insert_design`/`set_solution_type` already covers it and avoid
  double-setting.
- Let PyAEDT own launch-time version detection; pyEPR keeps
  `HfssProject._ansys_version` derived from `GetVersion()` for its existing
  `>=` string gates (unchanged semantics).

### Phase 4 — (Optional, later) idiomatic PyAEDT for *new* paths only
- New features may use `hfss.post.get_solution_data`, `hfss.setups`, modeler,
  etc. Do **not** rewrite the working `HfssModeler` (100+ methods, used by users
  building geometry, not by the EPR core) — let it ride the backend swap.

---

## 5. Cross-platform / gRPC gotchas (call them out now)

1. **Export-to-temp-file** (§2, §Phase 2) — *the* gotcha. Server-side files.
2. **Win32-specific types/calls** — `CDispatch` isinstance, `pythoncom`,
   `windll.IsUserAnAdmin`. Guard all three; they must be unreachable on pyaedt.
3. **Return-shape marshalling** — COM often returns tuples; the gRPC plugin
   returns lists. Audit consumers that index/`len()` results:
   `GetVariables()`, `ListVariations()`, `GetExcitations()`, `eigenmodes()`
   parsing (`ansys.py:1858-1877`).
4. **`set_mode` / `EditSources`** already branches on v2019 (`ansys.py` EM
   solutions) — verify PyAEDT doesn't normalize the signature differently.
5. **Non-graphical & licensing** — pyaedt path should support
   `non_graphical=True` for headless/CI-with-license runs; document the
   required AEDT + PyAEDT minimum versions.

---

## 6. Testing strategy

- **Contract/mock tests (CI, no license):** golden call-sequence for every
  `CalcObject` consumer; backend-selection unit tests with a fake backend.
- **`@pytest.mark.hfss` (COM, Windows):** existing oracle path, unchanged.
- **New `@pytest.mark.hfss` parametrized over `backend=["com","pyaedt"]`:** run
  manually on a licensed box (Windows for both; Linux for pyaedt/gRPC). Assert
  χ-matrix / eigenfrequencies match `correct_results.pkl` within tolerance —
  *equality of numerics across backends is the acceptance criterion.*
- **Import-isolation test:** assert `import pyEPR_pyaedt.solution_types` and
  `import pyEPR_pyaedt.calcs` succeed with neither `win32com` nor `ansys.aedt.core`
  importable (simulate Linux / no-extras).

---

## 7. Backwards-compatibility checklist

- [ ] `backend` is keyword-only, defaults to `"com"`; **no existing call site
      changes behavior.**
- [ ] No signature changes to `ProjectInfo` / `DistributedAnalysis` /
      `QuantumAnalysis`; deprecated aliases untouched.
- [ ] `ansys-aedt-core` stays in `[optional-dependencies] aedt`, never core.
- [ ] `solution_types.py` and `calcs/` remain import-clean on Linux.
- [ ] quantum-metal's `pyEPR-quantum >= 0.9.5` floor still satisfied; don't force
      a floor bump on them.

---

## 8. Suggested sequencing & effort (relative)

| Step | What | Size | Gate |
|---|---|---|---|
| **POC spike** | Connect via PyAEDT, run 1 eigenmode extraction through *unchanged* wrappers, assert identical numbers | S (1–2 d) | **Go/no-go for the whole plan** |
| Phase 0 | Extra dep, backend module, contract+import tests | S | CI green |
| Phase 1 | `PyAedtBackend`, route connect, guard win32 bits | M | hfss tests pass on COM still |
| Phase 2 | Field calc + export-file helper | M–L | numerics match on pyaedt |
| Phase 3 | Version handling tidy-up | S | 2024.x design creation correct |
| Phase 4 | (optional) idiomatic PyAEDT for new features | — | per-feature |

Release as an **additive minor** (e.g. `0.10.0`) once Phase 2 is proven; keep
default backend `"com"` until field-tested, then flip the default in a clearly
documented follow-up. Add a docs section / tutorial: *"Connecting to AEDT via
PyAEDT (Linux & gRPC)."*

---

## 9. Open decisions for the maintainer

1. **Scope:** adapter/optional-backend (recommended) vs. full rewrite to
   idiomatic PyAEDT?
2. **Default flip:** keep `"com"` default indefinitely, or switch to `"pyaedt"`
   once proven (and in which release)?
3. **End state for `win32com`:** keep both backends long-term, or deprecate the
   COM path eventually?
4. **Support floor:** minimum PyAEDT (`ansys-aedt-core`) and AEDT versions to
   commit to and test against.
5. **Q3D / modeler:** in-scope for the pyaedt backend now, or EPR-eigenmode path
   only first?
