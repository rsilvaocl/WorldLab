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


def test_viewer_groups_evidence_before_run_detail():
    source = viewer_source()
    assert 'id="evidenceStack"' in source
    assert 'Validez de la evidencia' in source
    assert 'id="detailStack"' in source
    assert 'Detalle de la corrida' in source
    assert 'Experiencias necesarias' in source
    assert 'Predicción sobre la celda nunca vivida' in source
