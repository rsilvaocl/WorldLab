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
