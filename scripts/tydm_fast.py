#!/usr/bin/env python3
"""tydm_fast.py — Backend MDT local ultraligero: TF-IDF + NB/kNN + conformal (REQ-027).

# REQ-027
Clasificador de decisiones tipadas 100% stdlib, sin red y sin GPU: features
TF (palabras, bigramas y char 4-grams con hashing crc32), modelo Naive Bayes
multinomial o kNN coseno (elegido por validacion cruzada), calibracion por
temperatura y abstencion conformal con cobertura garantizada. Se entrena con
el set validado del proyecto (`.docs/knowledge/ai/tydm_calibration_set.json`).

Las opciones candidatas de cada caso se respetan: en `choice` cada caso declara
sus criterios y la prediccion se restringe a ellos (re-normalizada); en `score`
las clases son los indices de nivel ("0".."N-1").

Uso:
    python3 scripts/tydm_fast.py train [--set F] [--out F]
    python3 scripts/tydm_fast.py predict --tipo noul --estado "..." --instrucciones "..." [--json]
    python3 scripts/tydm_fast.py bench [--folds 5] [--json]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
import unicodedata
import zlib
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tydm_calibration as tc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SET_PATH = ROOT / ".docs" / "knowledge" / "ai" / "tydm_calibration_set.json"
MODEL_PATH = ROOT / ".docs" / ".storage" / "tydm_fast_model.json"
TIPOS = ("noul", "choice", "score")
SEED = 20260925
N_BUCKETS = 1 << 16
ALPHA_NB = 0.1
K_VECINOS = 15
ALPHA_CONFORMAL = 0.10
GRID_TEMPERATURA = (0.25, 0.4, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0)


# --- features ---------------------------------------------------------------

def _normalizar(texto: str) -> str:
    """Minusculas y sin acentos (NFKD) para robustez morfologica."""
    plano = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in plano if not unicodedata.combining(c))


def _hash(feature: str) -> int:
    return zlib.crc32(feature.encode("utf-8")) % N_BUCKETS


def features(texto: str) -> dict[int, float]:
    """TF normalizado: palabras + bigramas + char 4-grams hashed a N_BUCKETS."""
    palabras = re.findall(r"[a-z0-9]+", _normalizar(texto))
    if not palabras:
        return {}
    conteo: dict[str, float] = {}
    for w in palabras:
        conteo["w:" + w] = conteo.get("w:" + w, 0.0) + 1.0
    for a, b in zip(palabras, palabras[1:]):
        cont = f"b:{a}_{b}"
        conteo[cont] = conteo.get(cont, 0.0) + 1.0
    for w in palabras:
        if len(w) >= 4:
            for i in range(len(w) - 3):
                cont = "c:" + w[i:i + 4]
                conteo[cont] = conteo.get(cont, 0.0) + 0.3
    total = sum(conteo.values()) or 1.0
    return {_hash(k): v / total for k, v in conteo.items()}


def _texto_caso(caso: dict[str, Any]) -> str:
    # Solo el texto del estado y la instruccion: las descripciones/claves de
    # criterios y los nombres de nivel actuan como ruido comun (verificado
    # el 2026-09-25: incluirlos baja choice 0.824->0.750 y score 0.676->0.583).
    return f"{caso.get('estado', '')} {caso.get('instrucciones', '')}"


def _dot(a: dict[int, float], b: dict[int, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(f, 0.0) for f, v in a.items())


def _candidatas_de_caso(caso: dict[str, Any]) -> list[str]:
    return tc._options_and_label(caso)[0]


# --- modelos ----------------------------------------------------------------

class _NBMultinomial:
    """Naive Bayes multinomial con suavizado de Laplace sobre features hashed."""

    nombre = "nb"

    def __init__(self) -> None:
        self.log_prior: dict[str, float] = {}
        self.log_probs: dict[str, dict[int, float]] = {}
        self.log_unseen: dict[str, float] = {}

    def entrenar(self, X: list[dict[int, float]], y: list[str], vocab: set[int]) -> None:
        conteos: dict[str, dict[int, float]] = {}
        prior: dict[str, int] = {}
        for feats, clase in zip(X, y):
            prior[clase] = prior.get(clase, 0) + 1
            bucket = conteos.setdefault(clase, {})
            for f, v in feats.items():
                bucket[f] = bucket.get(f, 0.0) + v
        n = len(X)
        V = max(len(vocab), 1)
        for clase, bucket in conteos.items():
            total = sum(bucket.values())
            denominador = total + ALPHA_NB * V
            self.log_prior[clase] = math.log(prior[clase] / n)
            self.log_unseen[clase] = math.log(ALPHA_NB / denominador)
            self.log_probs[clase] = {
                f: math.log((v + ALPHA_NB) / denominador) for f, v in bucket.items()
            }

    def logits(self, feats: dict[int, float]) -> dict[str, float]:
        salida = {}
        for clase, prior in self.log_prior.items():
            lp = self.log_probs[clase]
            unseen = self.log_unseen[clase]
            salida[clase] = prior + sum(v * lp.get(f, unseen) for f, v in feats.items())
        return salida


class _KNN:
    """kNN coseno sobre vectores TF normalizados (L2)."""

    nombre = "knn"

    def __init__(self) -> None:
        self.X: list[dict[int, float]] = []
        self.y: list[str] = []
        self.k = K_VECINOS

    def entrenar(self, X: list[dict[int, float]], y: list[str], vocab: set[int]) -> None:
        self.X = [self._l2(x) for x in X]
        self.y = list(y)

    @staticmethod
    def _l2(vec: dict[int, float]) -> dict[int, float]:
        norma = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {f: v / norma for f, v in vec.items()}

    def logits(self, feats: dict[int, float]) -> dict[str, float]:
        q = self._l2(feats)
        sims = sorted(
            ((_dot(q, x), clase) for x, clase in zip(self.X, self.y)),
            reverse=True,
        )[: self.k]
        salida: dict[str, float] = {clase: 0.0 for clase in set(self.y)}
        for sim, clase in sims:
            salida[clase] += max(sim, 0.0)
        return salida


def _crear_modelo(nombre: str) -> Any:
    return _NBMultinomial() if nombre == "nb" else _KNN()


# --- validacion, temperatura y conformal ------------------------------------

def _folds_estratificados(y: list[str], folds: int, rng: random.Random) -> list[list[int]]:
    por_clase: dict[str, list[int]] = {}
    for i, clase in enumerate(y):
        por_clase.setdefault(clase, []).append(i)
    asignacion: list[list[int]] = [[] for _ in range(folds)]
    for indices in por_clase.values():
        rng.shuffle(indices)
        for pos, i in enumerate(indices):
            asignacion[pos % folds].append(i)
    return asignacion


def _softmax_restringido(
    logits: dict[str, float], candidatas: list[str], temperatura: float
) -> dict[str, float]:
    sub = {c: logits.get(c, -1e9) for c in candidatas if c in logits or c in candidatas}
    valores = list(sub.values())
    probs = tc.softmax(valores, temperatura)
    return dict(zip(sub.keys(), probs))


def _ece_top(confs: list[float], aciertos: list[bool], n_bins: int = 10) -> float:
    """ECE top-label: |confianza - accuracy| por bin, ponderada."""
    if not confs:
        return 0.0
    total = len(confs)
    error = 0.0
    for b in range(n_bins):
        idx = [i for i, c in enumerate(confs) if min(int(c * n_bins), n_bins - 1) == b]
        if not idx:
            continue
        conf_bin = sum(confs[i] for i in idx) / len(idx)
        acc_bin = sum(1 for i in idx if aciertos[i]) / len(idx)
        error += (len(idx) / total) * abs(conf_bin - acc_bin)
    return error


def _cuantil_conformal(scores: list[float], alpha: float) -> float:
    n = len(scores)
    if n == 0:
        return 1.0
    k = math.ceil((n + 1) * (1 - alpha))
    if k > n:
        return 1.0
    return sorted(scores)[k - 1]


def _entrenar_tipo(
    casos_tipo: list[dict[str, Any]],
    folds: int,
    rng: random.Random,
    alpha: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    X: list[dict[int, float]] = []
    y: list[str] = []
    candidatas_por_caso: list[list[str]] = []
    for caso in casos_tipo:
        opts, label = tc._options_and_label(caso)
        X.append(features(_texto_caso(caso)))
        y.append(opts[label])
        candidatas_por_caso.append(opts)
    clases = sorted({c for opts in candidatas_por_caso for c in opts})

    # pruning: features con df >= 2 (reduce ruido y tamano del modelo)
    df: dict[int, int] = {}
    for feats in X:
        for f in feats:
            df[f] = df.get(f, 0) + 1
    X = [{f: v for f, v in feats.items() if df.get(f, 0) >= 2} for feats in X]
    vocab = set(df) if df else set()

    oof: dict[str, list[Any]] = {
        "nb": [None] * len(X),
        "knn": [None] * len(X),
    }
    for test_idx in _folds_estratificados(y, folds, rng):
        test_set = set(test_idx)
        train_idx = [i for i in range(len(X)) if i not in test_set]
        X_tr = [X[i] for i in train_idx]
        y_tr = [y[i] for i in train_idx]
        for nombre in ("nb", "knn"):
            modelo = _crear_modelo(nombre)
            modelo.entrenar(X_tr, y_tr, vocab)
            for i in test_idx:
                oof[nombre][i] = modelo.logits(X[i])

    def aciertos_con(nombre: str, temperatura: float) -> tuple[list[bool], list[float]]:
        aciertos: list[bool] = []
        confs: list[float] = []
        for lg, cands, clase in zip(oof[nombre], candidatas_por_caso, y):
            p = _softmax_restringido(lg, cands, temperatura)
            aciertos.append(max(p, key=p.get) == clase)
            confs.append(max(p.values()))
        return aciertos, confs

    acc_sel = {
        nombre: sum(aciertos_con(nombre, 1.0)[0]) / len(y) for nombre in ("nb", "knn")
    }
    elegido = "nb" if acc_sel["nb"] >= acc_sel["knn"] else "knn"
    logits_oof = oof[elegido]

    mejor_t, mejor_nll = 1.0, float("inf")
    for t in GRID_TEMPERATURA:
        nll_total = 0.0
        for lg, cands, clase in zip(logits_oof, candidatas_por_caso, y):
            p = _softmax_restringido(lg, cands, t)
            nll_total += tc.nll(list(p.values()), list(p.keys()).index(clase))
        if nll_total < mejor_nll:
            mejor_t, mejor_nll = t, nll_total
    temperatura = mejor_t

    probs_oof = [
        _softmax_restringido(lg, cands, temperatura)
        for lg, cands in zip(logits_oof, candidatas_por_caso)
    ]
    scores_nc = [1.0 - p[clase] for p, clase in zip(probs_oof, y)]
    q = _cuantil_conformal(scores_nc, alpha)

    modelo_final = _crear_modelo(elegido)
    modelo_final.entrenar(X, y, vocab)

    parametros: dict[str, Any] = {
        "algoritmo": elegido,
        "clases": clases,
        "temperatura": temperatura,
        "q_conformal": q,
        "alpha_conformal": alpha,
        "knn": (
            {"X": modelo_final.X, "y": modelo_final.y, "k": K_VECINOS}
            if elegido == "knn" else None
        ),
        "nb": (
            {
                "log_prior": modelo_final.log_prior,
                "log_probs": {
                    c: {str(f): v for f, v in d.items()}
                    for c, d in modelo_final.log_probs.items()
                },
                "log_unseen": modelo_final.log_unseen,
            }
            if elegido == "nb" else None
        ),
    }

    aciertos = [max(p, key=p.get) == clase for p, clase in zip(probs_oof, y)]
    confs = [max(p.values()) for p in probs_oof]
    emitidas = [
        i for i, p in enumerate(probs_oof)
        if sum(1 for pr in p.values() if pr >= 1.0 - q) == 1
    ]
    emitidas_correctas = sum(1 for i in emitidas if aciertos[i])
    hits = sum(aciertos)
    ic = tc.wilson_ci(hits, len(y))
    metricas: dict[str, Any] = {
        "n": len(y),
        "accuracy": hits / len(y),
        "ic95": [ic[0], ic[1]],
        "ece": _ece_top(confs, aciertos),
        "brier": sum(
            tc.brier(list(p.values()), list(p.keys()).index(clase))
            for p, clase in zip(probs_oof, y)
        ) / len(y),
        "algoritmo": elegido,
        "accuracy_nb": acc_sel["nb"],
        "accuracy_knn": acc_sel["knn"],
        "temperatura": temperatura,
        "q_conformal": q,
        "cobertura_conformal": sum(
            1 for p, clase in zip(probs_oof, y) if p[clase] >= 1.0 - q
        ) / len(y),
        "tasa_abstencion": 1.0 - len(emitidas) / len(y),
        "accuracy_emitidas": (emitidas_correctas / len(emitidas)) if emitidas else None,
    }
    return parametros, metricas


def entrenar(
    casos: list[dict[str, Any]],
    folds: int = 5,
    alpha: float = ALPHA_CONFORMAL,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(SEED)
    modelo: dict[str, Any] = {"version": 1, "seed": SEED, "tipos": {}}
    metricas: dict[str, Any] = {}
    for tipo in TIPOS:
        sub = [c for c in casos if c.get("tipo") == tipo]
        if len(sub) < folds:
            continue
        parametros, mex = _entrenar_tipo(sub, folds, rng, alpha)
        modelo["tipos"][tipo] = parametros
        metricas[tipo] = mex
    return modelo, metricas


# --- inferencia -------------------------------------------------------------

def _modelo_desde_json(datos_tipo: dict[str, Any]) -> Any:
    modelo = _crear_modelo(datos_tipo["algoritmo"])
    if datos_tipo["algoritmo"] == "nb":
        nb = datos_tipo["nb"]
        modelo.log_prior = nb["log_prior"]
        modelo.log_probs = {
            c: {int(f): v for f, v in d.items()} for c, d in nb["log_probs"].items()
        }
        modelo.log_unseen = nb["log_unseen"]
    else:
        knn = datos_tipo["knn"]
        modelo.X = knn["X"]
        modelo.y = knn["y"]
        modelo.k = knn["k"]
    return modelo


def predecir(
    modelo_json: dict[str, Any],
    tipo: str,
    estado: str,
    instrucciones: str,
    criterios: dict[str, str] | None = None,
    niveles: list[str] | None = None,
) -> dict[str, Any]:
    datos = modelo_json["tipos"][tipo]
    modelo = _modelo_desde_json(datos)
    caso = {"tipo": tipo, "estado": estado, "instrucciones": instrucciones}
    if criterios:
        caso["criterios"] = criterios
    if niveles:
        caso["niveles"] = niveles
    if criterios:
        candidatas = list(criterios.keys())
    elif niveles:
        candidatas = [str(i) for i in range(len(niveles))]
    else:
        candidatas = datos["clases"]

    inicio = time.perf_counter()
    feats = features(_texto_caso(caso))
    probs = _softmax_restringido(modelo.logits(feats), candidatas, datos["temperatura"])
    latencia_us = (time.perf_counter() - inicio) * 1e6

    q = datos["q_conformal"]
    conjunto = [c for c, p in probs.items() if p >= 1.0 - q]
    decision = max(probs, key=probs.get) if len(conjunto) == 1 else None
    resultado: dict[str, Any] = {
        "tipo": tipo,
        "backend": "fast-" + datos["algoritmo"],
        "probabilidades": probs,
        "decision": decision,
        "conjunto_conformal": conjunto,
        "temperatura": datos["temperatura"],
        "q_conformal": q,
        "revision_humana": decision is None,
        "experimental": True,
        "latencia_us": round(latencia_us, 1),
    }
    if tipo == "score" and niveles and decision is not None:
        resultado["nivel_texto"] = niveles[int(decision)]
    return resultado


# --- benchmark --------------------------------------------------------------

def bench(folds: int = 5, alpha: float = ALPHA_CONFORMAL, repeticiones: int = 20) -> dict[str, Any]:
    casos = tc.load_set(SET_PATH)
    inicio = time.perf_counter()
    modelo, metricas = entrenar(casos, folds=folds, alpha=alpha)
    tiempo_entrenamiento = time.perf_counter() - inicio
    tamano = len(json.dumps(modelo).encode("utf-8"))

    latencias: list[float] = []
    for caso in casos:
        for _ in range(repeticiones):
            r = predecir(
                modelo, caso["tipo"], caso["estado"], caso["instrucciones"],
                caso.get("criterios"), caso.get("niveles"),
            )
            latencias.append(r["latencia_us"])
    latencias.sort()

    total = sum(m["n"] for m in metricas.values())
    aciertos = sum(m["accuracy"] * m["n"] for m in metricas.values())
    return {
        "folds": folds,
        "alpha_conformal": alpha,
        "tiempo_entrenamiento_s": round(tiempo_entrenamiento, 3),
        "tamano_modelo_bytes": tamano,
        "latencia_us_p50": round(latencias[len(latencias) // 2], 1),
        "latencia_us_p95": round(latencias[int(len(latencias) * 0.95)], 1),
        "accuracy_global": aciertos / total,
        "por_tipo": metricas,
        "set": str(SET_PATH.relative_to(ROOT)),
        "version_set": json.loads(SET_PATH.read_text(encoding="utf-8")).get("version"),
    }


# --- CLI --------------------------------------------------------------------

def _print_bench(resultado: dict[str, Any]) -> None:
    print(f"tydm_fast bench  (set v{resultado['version_set']}, {resultado['folds']} folds, "
          f"alpha={resultado['alpha_conformal']})")
    print(f"entrenamiento: {resultado['tiempo_entrenamiento_s']} s | "
          f"modelo: {resultado['tamano_modelo_bytes'] / 1024:.0f} KB | "
          f"latencia p50: {resultado['latencia_us_p50']} us, p95: {resultado['latencia_us_p95']} us")
    print(f"accuracy global: {resultado['accuracy_global']:.3f}")
    for tipo, m in resultado["por_tipo"].items():
        print(f"  {tipo:<7} n={m['n']:<4} acc={m['accuracy']:.3f} "
              f"[{m['ic95'][0]:.3f},{m['ic95'][1]:.3f}] ece={m['ece']:.3f} "
              f"brier={m['brier']:.3f} cobertura={m['cobertura_conformal']:.3f} "
              f"abst={m['tasa_abstencion']:.3f} emitidas_acc={m['accuracy_emitidas']} "
              f"({m['algoritmo']}; nb={m['accuracy_nb']:.3f} knn={m['accuracy_knn']:.3f})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backend MDT local ultraligero (REQ-027)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_train = sub.add_parser("train", help="Entrena y guarda el modelo")
    p_train.add_argument("--set", default=str(SET_PATH))
    p_train.add_argument("--out", default=str(MODEL_PATH))
    p_train.add_argument("--folds", type=int, default=5)

    p_pred = sub.add_parser("predict", help="Predice un caso")
    p_pred.add_argument("--tipo", choices=TIPOS, required=True)
    p_pred.add_argument("--estado", required=True)
    p_pred.add_argument("--instrucciones", required=True)
    p_pred.add_argument("--criterios", help="JSON con criterios (choice)")
    p_pred.add_argument("--niveles", help="JSON con niveles (score)")
    p_pred.add_argument("--model", default=str(MODEL_PATH))
    p_pred.add_argument("--json", action="store_true")

    p_bench = sub.add_parser("bench", help="Validacion cruzada + latencia")
    p_bench.add_argument("--folds", type=int, default=5)
    p_bench.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "train":
        casos = tc.load_set(Path(args.set))
        modelo, metricas = entrenar(casos, folds=args.folds)
        salida = Path(args.out)
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_text(json.dumps(modelo, ensure_ascii=False), encoding="utf-8")
        print(f"tydm_fast: modelo entrenado ({len(casos)} casos) -> {salida}")
        for tipo, m in metricas.items():
            print(f"  {tipo}: acc={m['accuracy']:.3f} ece={m['ece']:.3f} "
                  f"({m['algoritmo']})")
        return 0

    if args.cmd == "predict":
        ruta = Path(args.model)
        if not ruta.exists():
            print(f"Error: no existe el modelo {ruta}; ejecuta 'train' primero", file=sys.stderr)
            return 1
        modelo = json.loads(ruta.read_text(encoding="utf-8"))
        resultado = predecir(
            modelo,
            args.tipo,
            args.estado,
            args.instrucciones,
            json.loads(args.criterios) if args.criterios else None,
            json.loads(args.niveles) if args.niveles else None,
        )
        if args.json:
            print(json.dumps(resultado, ensure_ascii=False, indent=2))
        else:
            print(f"decision: {resultado['decision']} "
                  f"(conjunto conformal: {resultado['conjunto_conformal']}, "
                  f"{resultado['latencia_us']} us)")
            for clase, p in sorted(resultado["probabilidades"].items(), key=lambda kv: -kv[1]):
                print(f"  {clase}: {p:.3f}")
        return 0

    resultado = bench(folds=args.folds)
    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        _print_bench(resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
