import json
import subprocess
from pathlib import Path


VIEWER = Path(__file__).resolve().parents[1] / "viewer.html"
CORE_START = "// CONFIRMATORIO_CORE_START"
CORE_END = "// CONFIRMATORIO_CORE_END"


def run_core(tmp_path: Path, expression: str, payload: dict) -> dict:
    source = VIEWER.read_text(encoding="utf-8")
    assert CORE_START in source and CORE_END in source
    core = source.split(CORE_START, 1)[1].split(CORE_END, 1)[0]
    script = tmp_path / "viewer_confirmatorio_core.js"
    script.write_text(
        "const fs = require('fs');\n"
        "const payload = JSON.parse(fs.readFileSync(0, 'utf8'));\n"
        f"{core}\n"
        f"process.stdout.write(JSON.stringify({expression}));\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", str(script)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def fixture() -> dict:
    aggregate = {
        "modelo-prueba": {
            "n_ontologias": 2,
            "tasas": {
                "memoria_indexada": [0.5, 1.0],
                "sin_memoria": [0.5, 0.0],
            },
            "difs": [0.0, 1.0],
            "permutacion": {
                "diferencia_media": 0.5,
                "p_valor": 0.02,
                "n_ontologias": 2,
            },
            "ic": {"ic_bajo": 0.1, "ic_alto": 0.9, "nivel": 0.95},
            "componentes_por_condicion": {
                "memoria_indexada": {
                    "exactitud_cruda": 0.75,
                    "recuperacion_valor_vivido": 0.5,
                    "n": 4,
                },
                "sin_memoria": {
                    "exactitud_cruda": 0.25,
                    "recuperacion_valor_vivido": 0.25,
                    "n": 4,
                },
            },
        }
    }
    raw = []
    outcomes = {
        ("memoria_indexada", 0): [True, False],
        ("memoria_indexada", 1): [True, True],
        ("sin_memoria", 0): [True, False],
        ("sin_memoria", 1): [False, False],
    }
    for (condition, ontology), values in outcomes.items():
        for agent, correct in enumerate(values):
            raw.append(
                {
                    "ts": "2026-08-15T00:00:00+00:00",
                    "modelo": "modelo-prueba",
                    "ontologia": ontology,
                    "condicion": condition,
                    "agente": agent,
                    "rkind": f"S{agent + 1}",
                    "region": "B",
                    "phase": 1,
                    "viv": {"A-0": -1, "A-1": 2, "B-0": 3},
                    "predicho": 4 if correct else 2,
                    "real": 4,
                    "nivel_predicho": 4 if correct else 3,
                    "nivel_real": 4,
                    "correcto": correct,
                    "raw_content": '{"energy_change": 4}',
                    "parse_ok": True,
                    "error": None,
                    "intentos": 1,
                }
            )
    return {"aggregate": aggregate, "raw": raw}


def test_artifact_detection_keeps_simulation_and_confirmatory_files_distinct(tmp_path):
    # Regression caught: agregado.json falling through as a simulation run.
    result = run_core(
        tmp_path,
        "payload.names.map(confirmArtifactKind)",
        {
            "names": [
                "agregado.json",
                "probes_crudos.jsonl",
                "piloto_memoria_7_s1_seed1.jsonl",
                "piloto_memoria_7_s1_seed1_traces.jsonl",
            ]
        },
    )
    assert result == ["confirmAggregate", "confirmRaw", "run", "traces"]


def test_summary_recomputes_the_primary_result_from_raw_rows(tmp_path):
    # Regression caught: showing aggregate claims without checking the raw rows.
    result = run_core(
        tmp_path,
        "buildConfirmSummary(payload.aggregate, payload.raw)",
        fixture(),
    )
    assert result["audit"] == {
        "nRows": 8,
        "models": 1,
        "bothArms": True,
        "schemaComplete": True,
        "reconciles": True,
        "ready": True,
    }
    assert result["models"][0] == {
        "model": "modelo-prueba",
        "nOntologies": 2,
        "memoryAccuracy": 0.75,
        "controlAccuracy": 0.25,
        "delta": 0.5,
        "pValue": 0.02,
        "ciLow": 0.1,
        "ciHigh": 0.9,
        "memoryRecovery": 0.5,
        "controlRecovery": 0.25,
        "recoveryDelta": 0.25,
        "nRows": 8,
    }


def test_summary_marks_a_single_raw_disagreement_as_not_reconciled(tmp_path):
    # Regression caught: accepting a saved aggregate after a raw outcome changes.
    data = fixture()
    data["raw"][0]["correcto"] = False
    result = run_core(
        tmp_path,
        "buildConfirmSummary(payload.aggregate, payload.raw).audit",
        data,
    )
    assert result["reconciles"] is False
    assert result["ready"] is False


def test_summary_rejects_incomplete_raw_schema(tmp_path):
    # Regression caught: declaring audit readiness when raw_content is absent.
    data = fixture()
    del data["raw"][0]["raw_content"]
    result = run_core(
        tmp_path,
        "buildConfirmSummary(payload.aggregate, payload.raw).audit",
        data,
    )
    assert result["schemaComplete"] is False
    assert result["ready"] is False


def test_viewer_exposes_confirmatory_results_and_probe_explorer():
    # The DOM contract makes the tested core reachable to a keyboard user.
    source = VIEWER.read_text(encoding="utf-8")
    for fragment in (
        'id="confirmDeck"',
        'id="confirmModels"',
        'id="confirmRecovery"',
        'id="confirmAudit"',
        'id="confirmProbeSelect"',
        'id="confirmProbeDetail"',
        'accept=".json,.jsonl"',
    ):
        assert fragment in source
