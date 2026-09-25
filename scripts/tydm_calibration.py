#!/usr/bin/env python3
"""tydm_calibration.py — Calibracion del motor MDT (REQ-011).

Ejecuta el set etiquetado, mide la calibracion de las probabilidades del motor
y ajusta una temperatura T (env TYDM_TEMPERATURE) por minimizacion del NLL.

Metodologia (fuentes):
- Guo et al. 2017, "On Calibration of Modern Neural Networks" (ICML,
  arXiv:1706.04599): temperature scaling (dividir logits por T) corrige la
  overconfidence sin cambiar el argmax.
- Nixon et al. 2019, "Measuring Calibration in Deep Learning"
  (arXiv:1904.01685): medir todas las probabilidades (NLL/Brier), ECE como
  metrica secundaria con caveats.
- Kadavath et al. 2022, "Language Models (Mostly) Know What They Know"
  (arXiv:2207.05221): los LLM son calibrables en eleccion multiple / si-no.

El T recomendado se ajusta sobre el set completo; para estimar la
generalizacion se reporta validacion cruzada k-fold (T se ajusta en el train
de cada fold y se evalua en el test held-out).

Uso:
    python3 scripts/tydm_calibration.py
    python3 scripts/tydm_calibration.py --set <set.json> --folds 5 --json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

from tydm_llama import TyDMLlama

DEFAULT_SET = Path(__file__).resolve().parent.parent / ".docs" / "knowledge" / "ai" / "tydm_calibration_set.json"
DEFAULT_REPORT = Path(__file__).resolve().parent.parent / ".docs" / ".storage" / "tydm_calibration.json"
DEFAULT_CACHE = Path(__file__).resolve().parent.parent / ".docs" / ".storage" / "tydm_calibration_cache.json"
EPS = 1e-12
# Grid de temperatura: suficiente para overconfidence tipica de LLM (T > 1).
GRID = [round(0.1 * i, 1) for i in range(1, 51)]  # 0.1 .. 5.0
# IC bootstrap de NLL/Brier (determinista por seed fijo, P1.9).
BOOTSTRAP_N = 500
BOOTSTRAP_SEED = 20260919


def _log(p: float) -> float:
    return math.log(max(p, EPS))


def softmax(values: list[float], temperature: float = 1.0) -> list[float]:
    """Softmax con escala por temperatura (T <= 0 invalido)."""
    if temperature <= 0:
        raise ValueError(f"temperature debe ser > 0, se recibio {temperature}")
    scaled = [v / temperature for v in values]
    mx = max(scaled)
    ex = [math.exp(v - mx) for v in scaled]
    s = sum(ex)
    return [e / s for e in ex]


def temperature_scale(probs: list[float], temperature: float) -> list[float]:
    """Reescala una distribucion ya normalizada aplicando T sobre sus logits.

    logits = log(p); p_T = softmax(logits / T). La constante de normalizacion
    se cancela, por lo que es equivalente a escalar los logits originales.
    """
    if temperature <= 0:
        raise ValueError(f"temperature debe ser > 0, se recibio {temperature}")
    return softmax([_log(p) for p in probs], temperature)


def brier(probs: list[float], label_idx: int) -> float:
    """Brier multiclase: suma (p_k - y_k)^2 (norma L2, Nixon et al. 2019)."""
    return sum((p - (1.0 if i == label_idx else 0.0)) ** 2 for i, p in enumerate(probs))


def nll(probs: list[float], label_idx: int) -> float:
    """Negative log-likelihood de la etiqueta correcta."""
    return -_log(probs[label_idx])


def ece(probs_list: list[list[float]], labels: list[int], n_bins: int = 10,
        adaptativo: bool = False) -> float:
    """Expected Calibration Error top-label (norma L1).

    Por defecto usa bins de igual anchura (equal-width). Con `adaptativo=True`
    usa bins de igual masa (equal-mass), que Nixon et al. 2019 recomiendan por
    su mayor estabilidad (metrica secundaria; reportar junto a NLL/Brier).
    """
    total = len(probs_list)
    if total == 0:
        return 0.0
    pares = [(max(p), p.index(max(p)) == label) for p, label in zip(probs_list, labels)]
    if adaptativo:
        pares.sort(key=lambda t: t[0])
        tam = max(1, math.ceil(total / n_bins))
        bins = [pares[i:i + tam] for i in range(0, total, tam)]
    else:
        bins = [[] for _ in range(n_bins)]
        for conf, correcto in pares:
            bins[min(int(conf * n_bins), n_bins - 1)].append((conf, correcto))
    e = 0.0
    for b in bins:
        if not b:
            continue
        conf = sum(c for c, _ in b) / len(b)
        acc = sum(1 for _, ok in b if ok) / len(b)
        e += (len(b) / total) * abs(acc - conf)
    return e


def _accuracy(probs_list: list[list[float]], labels: list[int]) -> float:
    if not probs_list:
        return 0.0
    hits = sum(1 for probs, label in zip(probs_list, labels) if probs.index(max(probs)) == label)
    return hits / len(probs_list)


def _hits(probs_list: list[list[float]], labels: list[int]) -> int:
    return sum(1 for probs, label in zip(probs_list, labels) if probs.index(max(probs)) == label)


def wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confianza de Wilson al 95 % para una proporcion (P0.1)."""
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    denom = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / denom
    margen = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return (max(0.0, centro - margen), min(1.0, centro + margen))


def evaluate(records: list[dict[str, Any]], temperature: float) -> dict[str, float]:
    """Metricas agregadas de un conjunto de records con temperatura T."""
    probs_list = [temperature_scale(r["probs"], temperature) for r in records]
    labels = [r["label_idx"] for r in records]
    n = len(records)
    if n == 0:
        return {
            "n": 0, "nll": 0.0, "brier": 0.0, "ece": 0.0, "ece_adaptativo": 0.0,
            "accuracy": 0.0, "accuracy_ci95": [0.0, 0.0], "confianza_media": 0.0,
        }
    hits = _hits(probs_list, labels)
    ci = wilson_ci(hits, n)
    return {
        "n": n,
        "nll": sum(nll(p, y) for p, y in zip(probs_list, labels)) / n,
        "brier": sum(brier(p, y) for p, y in zip(probs_list, labels)) / n,
        "ece": ece(probs_list, labels),
        "ece_adaptativo": ece(probs_list, labels, adaptativo=True),
        "accuracy": hits / n,
        "accuracy_ci95": [round(ci[0], 4), round(ci[1], 4)],
        "confianza_media": sum(max(p) for p in probs_list) / n,
    }


def fit_temperature(records: list[dict[str, Any]], grid: list[float] | None = None) -> float:
    """T que minimiza el NLL medio (Guo et al. 2017). Empate -> T mas cercano a 1."""
    grid = grid or GRID
    best_t = 1.0
    best_nll = math.inf
    for t in grid:
        m = evaluate(records, t)["nll"]
        if m < best_nll - 1e-12 or (abs(m - best_nll) <= 1e-12 and abs(t - 1.0) < abs(best_t - 1.0)):
            best_nll, best_t = m, t
    return best_t


def kfold(records: list[dict[str, Any]], folds: int, grid: list[float] | None = None,
          seed: int = 0) -> dict[str, float]:
    """Validacion cruzada: ajusta T en train, evalua en test held-out.

    Devuelve metricas medias out-of-fold a T=1 (antes) y con T ajustado (despues).
    """
    if folds < 2 or folds > len(records):
        raise ValueError(f"folds debe estar entre 2 y {len(records)}, se recibio {folds}")
    idx = list(range(len(records)))
    random.Random(seed).shuffle(idx)
    chunks = [idx[i::folds] for i in range(folds)]

    before: list[dict[str, float]] = []
    after: list[dict[str, float]] = []
    temps: list[float] = []
    for i in range(folds):
        test_idx = chunks[i]
        train_idx = [j for j in idx if j not in set(test_idx)]
        test = [records[j] for j in test_idx]
        train = [records[j] for j in train_idx]
        t = fit_temperature(train, grid)
        temps.append(t)
        before.append(evaluate(test, 1.0))
        after.append(evaluate(test, t))

    def mean(ms: list[dict[str, float]], key: str) -> float:
        return sum(m[key] for m in ms) / len(ms)

    return {
        "folds": folds,
        "T_media": sum(temps) / len(temps),
        "T_min": min(temps),
        "T_max": max(temps),
        "antes": {k: mean(before, k) for k in ("nll", "brier", "ece", "accuracy", "confianza_media")},
        "despues": {k: mean(after, k) for k in ("nll", "brier", "ece", "accuracy", "confianza_media")},
    }


def load_set(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    casos = data.get("casos")
    if not isinstance(casos, list) or not casos:
        raise ValueError(f"El set {path} no tiene una lista 'casos' no vacia")
    return casos


def _question(caso: dict[str, Any]) -> dict[str, Any]:
    tipo = caso["tipo"]
    q: dict[str, Any] = {"type": tipo, "instructions": caso["instrucciones"]}
    if tipo == "choice":
        q["criteria"] = caso["criterios"]
    elif tipo == "score":
        q["criteria"] = caso["niveles"]
    elif tipo != "noul":
        raise ValueError(f"{caso['id']}: tipo desconocido '{tipo}'")
    return q


def _options_and_label(caso: dict[str, Any]) -> tuple[list[str], int]:
    tipo = caso["tipo"]
    if tipo == "noul":
        options = ["yes", "no"]
    elif tipo == "choice":
        options = list(caso["criterios"].keys())
    else:  # score
        options = [str(i) for i in range(len(caso["niveles"]))]
    esperado = str(caso["esperado"])
    if esperado not in options:
        raise ValueError(f"{caso['id']}: esperado '{esperado}' no esta en {options}")
    return options, options.index(esperado)


def _clave_caso(modelo: str, caso: dict[str, Any]) -> str:
    return f"{modelo}|{caso['id']}"


def cargar_cache(path: Path | None = None) -> dict[str, Any]:
    ruta = Path(path or DEFAULT_CACHE)
    if ruta.exists():
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def guardar_cache(cache: dict[str, Any], path: Path | None = None) -> None:
    ruta = Path(path or DEFAULT_CACHE)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def sembrar_cache_desde_informe(cache: dict[str, Any], informe: Path | None = None) -> int:
    """Rellena la cache con las predicciones del ultimo informe (si existe)."""
    ruta = Path(informe or DEFAULT_REPORT)
    if not ruta.exists():
        return 0
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    modelo = str(datos.get("modelo", ""))
    n = 0
    for record in datos.get("records", []):
        clave = _clave_caso(modelo, record)
        if clave not in cache:
            cache[clave] = {"probs": record["probs"], "label_idx": record["label_idx"]}
            n += 1
    return n


def run_cases(
    client: TyDMLlama, casos: list[dict[str, Any]], cache: dict[str, Any] | None = None,
    modelo: str | None = None,
) -> list[dict[str, Any]]:
    """Ejecuta el motor sobre el set y devuelve records con probabilidades.

    Con `cache` reutiliza las predicciones previas (clave `<modelo>|<id>`), lo
    que acelera las re-calibraciones cuando solo cambian algunos casos.
    """
    nombre = modelo or Path(client.model_path).name
    records: list[dict[str, Any]] = []
    for caso in casos:
        options, label_idx = _options_and_label(caso)
        clave = _clave_caso(nombre, caso)
        if cache is not None and clave in cache:
            probs = [float(p) for p in cache[clave]["probs"]]
        else:
            result = client.decide(caso["estado"], {"q": _question(caso)})["q"]
            probs_map = result["probabilities"]
            probs = [float(probs_map[o]) for o in options]
            if cache is not None:
                cache[clave] = {"probs": probs, "label_idx": label_idx}
        records.append({
            "id": caso["id"],
            "tipo": caso["tipo"],
            "options": options,
            "probs": probs,
            "label_idx": label_idx,
            "pred": options[probs.index(max(probs))],
        })
    return records


def _por_tipo(records: list[dict[str, Any]], temperature: float) -> dict[str, dict[str, float]]:
    tipos = sorted({r["tipo"] for r in records})
    return {t: evaluate([r for r in records if r["tipo"] == t], temperature) for t in tipos}


def _valores_por_caso(records: list[dict[str, Any]], temperature: float) -> tuple[list[float], list[float]]:
    probs_list = [temperature_scale(r["probs"], temperature) for r in records]
    labels = [r["label_idx"] for r in records]
    nlls = [nll(p, y) for p, y in zip(probs_list, labels)]
    briers = [brier(p, y) for p, y in zip(probs_list, labels)]
    return nlls, briers


def bootstrap_ci(valores: list[float], n: int | None = None, seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    """IC 95 % por bootstrap (percentil) de la media de `valores` (determinista)."""
    if not valores:
        return (0.0, 0.0)
    rng = random.Random(seed)
    k = len(valores)
    remuestras = n or BOOTSTRAP_N
    medias = sorted(sum(valores[rng.randrange(k)] for _ in range(k)) / k for _ in range(remuestras))
    lo = medias[max(0, int(0.025 * remuestras))]
    hi = medias[min(remuestras - 1, int(0.975 * remuestras))]
    return (round(lo, 4), round(hi, 4))


def calibrate(
    client: TyDMLlama, casos: list[dict[str, Any]], folds: int = 5,
    cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    records = run_cases(client, casos, cache)
    t_full = fit_temperature(records)
    nll_t1, brier_t1 = _valores_por_caso(records, 1.0)
    nll_tr, brier_tr = _valores_por_caso(records, t_full)
    return {
        "modelo": client.model_path.name,
        "n_casos": len(records),
        "fuentes": "Guo 2017 arXiv:1706.04599; Nixon 2019 arXiv:1904.01685; Kadavath 2022 arXiv:2207.05221",
        "T_recomendada": t_full,
        "T1_set_completo": evaluate(records, 1.0),
        "T_recomendada_set_completo": evaluate(records, t_full),
        "bootstrap": {
            "n": BOOTSTRAP_N,
            "seed": BOOTSTRAP_SEED,
            "nll_ci95_T1": bootstrap_ci(nll_t1),
            "nll_ci95_Trecomendada": bootstrap_ci(nll_tr),
            "brier_ci95_T1": bootstrap_ci(brier_t1),
            "brier_ci95_Trecomendada": bootstrap_ci(brier_tr),
        },
        "validacion_cruzada": kfold(records, folds),
        "por_tipo_T1": _por_tipo(records, 1.0),
        "por_tipo_Trecomendada": _por_tipo(records, t_full),
        "records": records,
    }


def _print_human(report: dict[str, Any]) -> None:
    print(f"Modelo: {report['modelo']}")
    print(f"Casos:  {report['n_casos']}")
    print(f"T recomendada: {report['T_recomendada']}")
    print()
    print(f"{'metrica':<16}{'T=1':>10}{'T='+str(report['T_recomendada']):>10}")
    for k in ("nll", "brier", "ece", "accuracy", "confianza_media"):
        print(f"{k:<16}{report['T1_set_completo'][k]:>10.4f}{report['T_recomendada_set_completo'][k]:>10.4f}")
    b = report.get("bootstrap")
    if b:
        print(
            f"  IC95 bootstrap (n={b['n']})  NLL {b['nll_ci95_T1']} -> {b['nll_ci95_Trecomendada']}  "
            f"Brier {b['brier_ci95_T1']} -> {b['brier_ci95_Trecomendada']}"
        )
    cv = report["validacion_cruzada"]
    print()
    print(f"Validacion cruzada ({cv['folds']} folds, T media {cv['T_media']:.2f}):")
    print(f"  {'metrica':<16}{'antes':>10}{'despues':>10}")
    for k in ("nll", "brier", "ece", "accuracy", "confianza_media"):
        print(f"  {k:<16}{cv['antes'][k]:>10.4f}{cv['despues'][k]:>10.4f}")
    print()
    print("Por tipo (T recomendada):")
    for tipo, m in report["por_tipo_Trecomendada"].items():
        ci = m.get("accuracy_ci95", [0.0, 0.0])
        print(
            f"  {tipo:<8} n={m['n']:<3} acc={m['accuracy']:.3f} "
            f"[{ci[0]:.3f},{ci[1]:.3f}] ece={m['ece']:.3f} "
            f"ece_adapt={m.get('ece_adaptativo', 0.0):.3f} nll={m['nll']:.3f}"
        )
    print()
    print(f"Para aplicar: export TYDM_TEMPERATURE={report['T_recomendada']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibra el motor MDT (REQ-011)")
    parser.add_argument("--set", default=str(DEFAULT_SET), help="Ruta del set etiquetado")
    parser.add_argument("--folds", type=int, default=5, help="Folds de validacion cruzada")
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    parser.add_argument("--write", action="store_true", help=f"Escribe informe en {DEFAULT_REPORT}")
    parser.add_argument("--model", default=None, help="Ruta al GGUF (default: TYDM_MODEL_PATH o cache)")
    parser.add_argument("--no-cache", action="store_true", help="Ignorar la cache de predicciones")
    args = parser.parse_args()

    casos = load_set(Path(args.set))
    client = TyDMLlama(model_path=args.model)
    cache: dict[str, Any] | None = None
    if not args.no_cache:
        cache = cargar_cache()
        if not cache:
            sembrar_cache_desde_informe(cache)
    report = calibrate(client, casos, folds=args.folds, cache=cache)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human(report)

    if cache is not None:
        guardar_cache(cache)
    if args.write:
        DEFAULT_REPORT.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Informe escrito en {DEFAULT_REPORT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
