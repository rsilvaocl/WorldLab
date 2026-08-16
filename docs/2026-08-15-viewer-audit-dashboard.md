# Viewer Audit Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each WorldLab run immediately auditable in `viewer.html`, with an explicit evidence state, guided sibling-file recovery and accessible plain-language orientation.

**Architecture:** Keep the zero-dependency, single-file viewer and its current instrument aesthetic. Add a small evidence-status model in the existing script that derives a conservative audit state from `traces`, `probes`, `never_lived` and `underexposed()`. Render that model both in a new top-level audit summary and in the existing annunciators; no scientific conclusion is inferred beyond the evidence currently loaded.

**Tech Stack:** HTML5, CSS, vanilla browser JavaScript, Python `pytest` for repository regression coverage.

**Spec:** `docs/superpowers/specs/2026-08-15-viewer-dashboard-design.md`

## Global Constraints

- Keep `viewer.html` as a single file, with no build step, CDN or runtime dependency; it must work over `file://`.
- Escape every value originating in JSONL before inserting it with `innerHTML`.
- Do not change engine code, JSONL schemas, experiment data or scientific scoring.
- Do not hide failed events by default; `okOnly` remains `false` on load.
- Never call a run successful from the dashboard: `Lista para revisar` only means the required evidence is present and has no current integrity warning.
- Preserve current color semantics and provide text alongside every status color.

---

### Task 1: Lock the dashboard contract in a browser-free regression check

**Files:**
- Create: `tests/test_viewer_dashboard.py`
- Modify: `viewer.html: rail, dashboard markup, accessibility hooks, audit-state script`

**Interfaces:**
- Consumes: UTF-8 source text from `viewer.html`.
- Produces: `viewer_source()` and static contract tests that protect the required IDs, state labels, keyboard help and default failure visibility.

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


VIEWER = Path(__file__).resolve().parents[1] / "viewer.html"


def viewer_source() -> str:
    return VIEWER.read_text(encoding="utf-8")


def test_viewer_exposes_the_audit_dashboard_contract():
    source = viewer_source()
    for fragment in (
        'id="auditSummary"',
        'id="auditStatus"',
        'id="auditReasons"',
        'function auditState()',
        'Incompleta',
        'No interpretable',
        'Lista para revisar',
        'Agregar archivos',
    ):
        assert fragment in source


def test_viewer_keeps_failures_visible_and_documents_keyboard_navigation():
    source = viewer_source()
    assert 'let okOnly = false' in source
    assert 'Mostrar solo acciones logradas' in source
    assert 'Espacio reproduce o pausa' in source
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `python -m pytest tests/test_viewer_dashboard.py -v`

Expected: FAIL because the audit-dashboard IDs, function and copy do not yet exist.

- [ ] **Step 3: Add the minimal semantic dashboard shell and test-facing status model**

Add a `<header>` around the existing `#rail`; add a `<main id="workspace">` around the dashboard body; insert after the header a `section#auditSummary` containing `#auditStatus`, `#auditMessage`, `#auditReasons` and an `#addEvidenceBtn` button. Define `auditState()` with this exact return shape:

```js
{
  kind: 'empty' | 'incomplete' | 'invalid' | 'ready',
  label: 'Sin corrida' | 'Incompleta' | 'No interpretable' | 'Lista para revisar',
  message: string,
  reasons: Array<{ label: string, detail: string, target: string }>,
  needsFiles: boolean
}
```

The precedence is exact: no snapshots → `empty`; missing traces or probes → `incomplete`; no `never_lived` probe or any `underexposed()` agent → `invalid`; otherwise → `ready`. Keep the file action hidden when `needsFiles` is false.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python -m pytest tests/test_viewer_dashboard.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the contract and shell**

```bash
git add viewer.html tests/test_viewer_dashboard.py
git commit -m "feat: add viewer audit dashboard shell"
```

### Task 2: Render evidence state and support adding sibling files without resetting the run

**Files:**
- Modify: `viewer.html: ingest(), applyBundle(), fillAnnun(), fillCal(), event listeners`
- Test: `tests/test_viewer_dashboard.py`

**Interfaces:**
- Consumes: `auditState()` and current global `snaps`, `traces`, `probes`, `underexposed()`.
- Produces: `fillAuditSummary()`, `openEvidencePicker()` and target-scrolling behavior shared by summary reasons and lamps.

- [ ] **Step 1: Extend the failing test with recovery and conservative-state assertions**

```python
def test_viewer_retains_the_run_when_adding_sibling_evidence():
    source = viewer_source()
    assert 'function openEvidencePicker()' in source
    assert "$('addEvidenceBtn').onclick = openEvidencePicker" in source
    assert "if (b.run)" in source
    assert "traces = []; probes = [];" in source


def test_viewer_does_not_equate_readiness_with_experimental_success():
    source = viewer_source()
    assert 'evidencia completa para revisión' in source
    assert 'no afirma que el resultado sea positivo' in source
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest tests/test_viewer_dashboard.py -v`

Expected: FAIL because the recovery handler and explicit readiness caveat do not yet exist.

- [ ] **Step 3: Implement audit rendering and sibling-file recovery**

Implement the following behavior:

```js
function openEvidencePicker(){
  $('fileInput').click();
}

function scrollToInstrument(id){
  const target = $(id);
  if (!target) return;
  target.scrollIntoView({ behavior:'smooth', block:'center' });
  target.focus({ preventScroll:true });
}
```

Give every instrument that can be a navigation target `tabindex="-1"`. Make `fillAuditSummary()` clear and rebuild the reasons using `esc()` and buttons with `data-go`. Its copy must say:

- missing traces: `Faltan trazas: no se puede revisar qué respondió el modelo.`
- missing probes: `Falta el probe: no se puede revisar la predicción sobre la celda nunca vivida.`
- invalid held-out probe: `El probe no marca una celda nunca vivida.`
- underexposure: `Hay agentes sin las experiencias mínimas para interpretar su probe.`
- ready: `La evidencia está completa para revisión; no afirma que el resultado sea positivo.`

Modify `applyBundle()` only so a new primary run resets sibling state. If the picker supplies only traces/probes, leave `meta`, snapshots, events, `runName` and the current frame untouched; refresh `fillCal()`, `fillAuditSummary()`, `fillAnnun()` and `updateFrame()`.

Use `auditState()` to generate the relevant existing lamps, retaining their current per-instrument detail. Add `Agregar archivos` only for missing sibling evidence, and display the exact two expected file names in the dashboard help.

- [ ] **Step 4: Run focused tests and the complete Python suite**

Run: `python -m pytest tests/test_viewer_dashboard.py -v && python -m pytest`

Expected: both commands PASS.

- [ ] **Step 5: Commit the evidence workflow**

```bash
git add viewer.html tests/test_viewer_dashboard.py
git commit -m "feat: surface viewer evidence status"
```

### Task 3: Reorder the visual hierarchy and translate the two scientific instruments

**Files:**
- Modify: `viewer.html: CSS for #auditSummary/#stack groups; right-column markup; fillQuad(); fillCal()`
- Test: `tests/test_viewer_dashboard.py`

**Interfaces:**
- Consumes: the existing `#expoInst`, `#calInst`, `#clockInst`, `#energyInst`, `#borderInst`, `#crewInst`, `#tapeInst`.
- Produces: `#evidenceStack` and `#detailStack` labels; human-first subtitles without changing instrument data.

- [ ] **Step 1: Extend the failing test for hierarchy and language**

```python
def test_viewer_groups_evidence_before_run_detail():
    source = viewer_source()
    assert 'id="evidenceStack"' in source
    assert 'Validez de la evidencia' in source
    assert 'id="detailStack"' in source
    assert 'Detalle de la corrida' in source
    assert 'Experiencias necesarias' in source
    assert 'Predicción sobre la celda nunca vivida' in source
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest tests/test_viewer_dashboard.py -v`

Expected: FAIL because those semantic groups and human-first labels do not yet exist.

- [ ] **Step 3: Implement the two right-column groups and explanatory copy**

Wrap `#expoInst` and `#calInst` inside `#evidenceStack`, preceded by a non-card group label `Validez de la evidencia` and the short explanation `Lo necesario para saber si el resultado final se puede interpretar.` Wrap the remaining instrument cards inside `#detailStack`, labeled `Detalle de la corrida` with the explanation `Así transcurrió el mundo y qué hicieron los agentes.`

Change only the visible labels:

```html
<h2>Experiencias necesarias</h2>
<span class="sup">Exposición</span>

<h2>Predicción sobre la celda nunca vivida</h2>
<span class="sup">Probe de composición</span>
```

Keep the current four-cell chart and calibration scale intact. Add plain-language help below the exposure chart: `La celda rayada nunca se puede vivir. Para interpretar el probe, cada agente necesita al menos 3 consumos en las otras tres celdas.` Keep D-025 as an optional technical parenthetical, not the only explanation.

Style group labels as engraved placards and use a subtle divider/gap; do not add glossy cards, gradients or a second visual system. On `max-width:900px`, preserve evidence before detail in document order.

- [ ] **Step 4: Run focused and full tests**

Run: `python -m pytest tests/test_viewer_dashboard.py -v && python -m pytest`

Expected: PASS.

- [ ] **Step 5: Commit the visual hierarchy**

```bash
git add viewer.html tests/test_viewer_dashboard.py
git commit -m "feat: prioritize viewer evidence panels"
```

### Task 4: Clarify controls and finish the accessibility pass

**Files:**
- Modify: `viewer.html: transport markup, #drop markup, canvas markup, updateFrame(), drag events, filter handler, CSS`
- Test: `tests/test_viewer_dashboard.py`

**Interfaces:**
- Consumes: `okOnly`, `frame`, `snaps`, existing keyboard event handlers.
- Produces: `updateCanvasSummary(snapshot, phase, agents)`, accessible drag state and unambiguous filter copy.

- [ ] **Step 1: Extend the failing test for controls and accessibility**

```python
def test_viewer_has_landmarks_dynamic_canvas_summary_and_accessible_drop_state():
    source = viewer_source()
    for fragment in (
        '<header',
        '<main',
        '<aside',
        'id="canvasSummary"',
        'function updateCanvasSummary(',
        "drop.setAttribute('aria-hidden', 'false')",
        "drop.setAttribute('aria-hidden', 'true')",
    ):
        assert fragment in source


def test_viewer_filter_copy_describes_its_action():
    source = viewer_source()
    assert 'Mostrar solo acciones logradas' in source
    assert 'Mostrar todos los intentos' in source
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest tests/test_viewer_dashboard.py -v`

Expected: FAIL because the dynamic canvas summary and explicit drag state do not yet exist.

- [ ] **Step 3: Implement semantic and control improvements**

Use `header`, `main` and `aside` landmarks while keeping current layout selectors valid. Change the boot title to `<h2>` so it follows the page `<h1>`. Place `#canvasSummary` as a visually hidden `aria-live="polite"` element and call this exact function at the end of `updateFrame()`:

```js
function updateCanvasSummary(snapshot, phase, agents){
  const alive = agents.filter(agent => {
    const info = (snapshot.agents && snapshot.agents[agent.eid]) || {};
    return (info.energy || 0) > 0;
  }).length;
  $('canvasSummary').textContent =
    `Día ${snapshot.day}, tick ${snapshot.tick}, fase ${phaseName(phase).toLowerCase()}. ` +
    `${alive} de ${agents.length} agentes con energía.`;
}
```

Keep `canvas` labeled by `aria-describedby="canvasSummary"`. Replace the filter’s initial label with `Mostrar solo acciones logradas`, then set it to `Mostrar todos los intentos` only while failed attempts are being hidden; retain `aria-pressed`.

Add a visible transport hint: `Espacio reproduce o pausa · ←/→ un momento · Mayús+←/→ diez · Inicio/Fin extremos.`

Centralize drag-overlay changes in `setDropActive(active)` so CSS `data-on` and `aria-hidden` are always updated together. Call it from `dragenter`, `dragleave` and `drop`.

- [ ] **Step 4: Run validation, then inspect the changed source**

Run: `python -m pytest tests/test_viewer_dashboard.py -v && python -m pytest && node --check viewer.html`

Expected: Python tests PASS. `node --check viewer.html` is not valid for an HTML file; instead extract the inline script in a temporary file using a read-only command, then run `node --check` on that file. The extracted JavaScript must parse without syntax errors.

Run the following parse check:

```bash
node -e "const fs=require('fs');const h=fs.readFileSync('viewer.html','utf8');const s=h.match(/<script>([\\s\\S]*)<\\/script>/)[1];new Function(s);console.log('viewer script parses')"
```

Expected: prints `viewer script parses`.

- [ ] **Step 5: Commit the completed dashboard**

```bash
git add viewer.html tests/test_viewer_dashboard.py
git commit -m "feat: improve viewer dashboard accessibility"
```

### Task 5: Verify the delivered experience with representative local files

**Files:**
- Modify: none unless verification exposes a defect.
- Test: `tests/test_viewer_dashboard.py`, full `tests/` suite, local JSONL fixtures in `data/silver/`.

**Interfaces:**
- Consumes: completed `viewer.html`, one primary JSONL, its `_traces.jsonl` sibling and its `_probes.jsonl` sibling.
- Produces: documented verification outcome; no new product behavior.

- [ ] **Step 1: Run automated regression checks**

Run: `python -m pytest && node -e "const fs=require('fs');const h=fs.readFileSync('viewer.html','utf8');const s=h.match(/<script>([\\s\\S]*)<\\/script>/)[1];new Function(s);console.log('viewer script parses')"`

Expected: all tests PASS and JavaScript parser prints `viewer script parses`.

- [ ] **Step 2: Perform local manual checks**

Open `viewer.html` directly and test two bundles:

1. Drop only a primary `*_seed<N>.jsonl`: verify `Incompleta`, both missing sibling explanations and `Agregar archivos`; then add the sibling files and verify the visible world/frame remains loaded.
2. Drop the primary plus `_traces.jsonl` and `_probes.jsonl`: verify either `No interpretable` with a reason pointing to exposure/calibration or `Lista para revisar` with the explicit no-success caveat.

Use the keyboard to load, play/pause, move one/ten steps, jump to the endpoints and toggle the failed-event filter. Confirm its labels precisely describe the current action.

- [ ] **Step 3: Perform responsive visual verification when a local server is available**

Run: `python -m http.server 8000 --bind 127.0.0.1`

Expected: local server starts. Inspect at 1440px and 390px width; evidence appears before detail, no clipped summary, all text is readable and no horizontal scrolling appears at mobile width. If a local server cannot be started under the current execution environment, record that limitation and do not claim this visual pass was performed.

- [ ] **Step 4: Commit only if verification required a corrective change**

```bash
git add viewer.html tests/test_viewer_dashboard.py
git commit -m "fix: resolve viewer dashboard verification issue"
```
