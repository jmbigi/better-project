#!/usr/bin/env python3
"""index_knowledge.py — Indexa .docs/knowledge/ para búsqueda semántica local (REQ-002).

Genera chunks por seccion H2 de cada archivo Markdown y los guarda en
.docs/.storage/. Dos backends:

- chroma   (recomendado): ChromaDB + sentence-transformers (all-MiniLM-L6-v2),
  todo local. Se usa si ambos paquetes estan instalados.
- json     (sin dependencias): indice de palabras clave con scoring TF-IDF
  en .docs/.storage/index.json. Misma interfaz de consulta.

Incremental: solo re-indexa archivos con mtime cambiado (manifest en .storage).

Uso:
    python scripts/index_knowledge.py            # indexa (incremental)
    python scripts/index_knowledge.py --all      # fuerza re-indexado completo
    python scripts/index_knowledge.py --check    # verifica que el indice existe
    python scripts/index_knowledge.py search "tiempo de espera"
"""

import json
import math
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / ".docs" / "knowledge"
STORAGE_DIR = ROOT / ".docs" / ".storage"
MANIFEST = STORAGE_DIR / "manifest.json"
JSON_INDEX = STORAGE_DIR / "index.json"
SQLITE_DB = STORAGE_DIR / "knowledge.db"
CHROMA_DIR = STORAGE_DIR / "chroma_db"
MODEL_NAME = "all-MiniLM-L6-v2"

STOPWORDS = {
    "el", "la", "los", "las", "de", "del", "y", "o", "u", "a", "en", "con",
    "para", "por", "que", "un", "una", "es", "al", "lo", "como", "se", "su",
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "is",
}


def _chunks(text: str) -> list[str]:
    """Divide por H2 (##). Sin H2, el archivo completo es un chunk."""
    sections = re.split(r"\n##\s+", text, flags=re.M)
    return [s.strip() for s in sections if len(s.strip()) > 20]


def _tokenize(text: str) -> list[str]:
    return [
        w
        for w in re.findall(r"[a-záéíóúñ0-9]+", text.lower())
        if w not in STOPWORDS and len(w) > 1
    ]


def _files() -> list[Path]:
    if not KNOWLEDGE_DIR.is_dir():
        return []
    return sorted(p for p in KNOWLEDGE_DIR.rglob("*.md") if p.is_file())


def _chroma_available() -> bool:
    try:
        import chromadb  # noqa: F401
        import sentence_transformers  # noqa: F401

        return True
    except ImportError:
        return False


def _sqlite_available() -> bool:
    """SQLite con FTS5 esta disponible en stdlib (Python 3.11+)."""
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE test USING fts5(content)")
        conn.close()
        return True
    except Exception:
        return False


def _init_sqlite_db(conn: sqlite3.Connection) -> None:
    """Inicializa esquema: tabla chunks + FTS5 + tabla vectores TF-IDF."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            archivo TEXT NOT NULL,
            contenido TEXT NOT NULL,
            tokens TEXT NOT NULL,  -- JSON array de tokens
            mtime REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            contenido,
            content='chunks',
            content_rowid='rowid'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vectors (
            chunk_id TEXT PRIMARY KEY,
            vector TEXT NOT NULL,  -- JSON dict term->weight
            FOREIGN KEY(chunk_id) REFERENCES chunks(id)
        )
    """)
    # Triggers para mantener FTS5 sincronizado
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, contenido) VALUES (new.rowid, new.contenido);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, contenido) VALUES ('delete', old.rowid, old.contenido);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, contenido) VALUES ('delete', old.rowid, old.contenido);
            INSERT INTO chunks_fts(rowid, contenido) VALUES (new.rowid, new.contenido);
        END
    """)
    conn.commit()


def build_sqlite_index() -> tuple[int, int]:
    """Indice SQLite FTS5 + vectores TF-IDF en stdlib."""
    files = _files()
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    _init_sqlite_db(conn)

    manifest: dict = {}
    doc_count = len(files)
    all_tokens: list[list[str]] = []
    chunk_data: list[tuple[str, str, str, list[str], float]] = []  # id, archivo, contenido, tokens, mtime

    for path in files:
        mtime = path.stat().st_mtime
        manifest[str(path.relative_to(KNOWLEDGE_DIR))] = mtime
        text = path.read_text(encoding="utf-8", errors="replace")
        for idx, chunk in enumerate(_chunks(text)):
            tokens = _tokenize(chunk)
            all_tokens.append(tokens)
            chunk_id = _chunk_id(path, idx)
            chunk_data.append((chunk_id, f".docs/knowledge/{path.relative_to(KNOWLEDGE_DIR)}", chunk, tokens, mtime))

    # Calcular DF para TF-IDF
    df: dict[str, int] = {}
    for tokens in all_tokens:
        for term in set(tokens):
            df[term] = df.get(term, 0) + 1

    def tfidf(tokens: list[str]) -> dict[str, float]:
        tf: dict[str, float] = {}
        for term in tokens:
            tf[term] = tf.get(term, 0) + 1
        total = len(tokens) or 1
        return {
            term: (count / total) * math.log(1 + doc_count / (1 + df.get(term, 0)))
            for term, count in tf.items()
        }

    # Insertar chunks y vectores
    for chunk_id, archivo, contenido, tokens, mtime in chunk_data:
        vector = tfidf(tokens)
        conn.execute(
            "INSERT OR REPLACE INTO chunks (id, archivo, contenido, tokens, mtime) VALUES (?, ?, ?, ?, ?)",
            (chunk_id, archivo, contenido, json.dumps(tokens), mtime)
        )
        conn.execute(
            "INSERT OR REPLACE INTO vectors (chunk_id, vector) VALUES (?, ?)",
            (chunk_id, json.dumps(vector))
        )

    # Limpiar chunks obsoletos (archivos eliminados)
    existing_ids = {cd[0] for cd in chunk_data}
    for row in conn.execute("SELECT id FROM chunks"):
        if row["id"] not in existing_ids:
            conn.execute("DELETE FROM chunks WHERE id = ?", (row["id"],))
            conn.execute("DELETE FROM vectors WHERE chunk_id = ?", (row["id"],))

    MANIFEST.write_text(json.dumps(manifest), encoding="utf-8")
    conn.commit()
    conn.close()
    return len(files), len(chunk_data)


def search_sqlite(query: str, k: int = 5) -> list[dict]:
    """Busca combinando FTS5 (BM25) + similitud coseno TF-IDF."""
    qtokens = _tokenize(query)
    if not qtokens:
        return []

    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row

    # 1. FTS5 BM25 ranking (busqueda textual rapida)
    fts_query = " ".join(qtokens)
    fts_results = list(conn.execute(
        "SELECT rowid, bm25(chunks_fts) as bm25_score FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25_score LIMIT ?",
        (fts_query, k * 3)  # traer mas candidatos para rerank
    ))

    if not fts_results:
        conn.close()
        return []

    # 2. Rerank con similitud coseno TF-IDF sobre candidatos
    candidate_rowids = [row["rowid"] for row in fts_results]
    placeholders = ",".join("?" * len(candidate_rowids))
    chunks_rows = list(conn.execute(
        f"SELECT rowid, id, archivo, contenido FROM chunks WHERE rowid IN ({placeholders})",
        candidate_rowids
    ))
    vectors_rows = list(conn.execute(
        f"SELECT chunk_id, vector FROM vectors WHERE chunk_id IN (SELECT id FROM chunks WHERE rowid IN ({placeholders}))",
        candidate_rowids
    ))

    conn.close()

    # Mapa chunk_id -> vector
    vec_map = {row["chunk_id"]: json.loads(row["vector"]) for row in vectors_rows}
    # Mapa rowid -> bm25_score
    bm25_map = {row["rowid"]: row["bm25_score"] for row in fts_results}

    # Vector de consulta (TF simple)
    qvec = {term: 1.0 for term in qtokens}

    results = []
    for chunk_row in chunks_rows:
        chunk_id = chunk_row["id"]
        rowid = chunk_row["rowid"]
        vector = vec_map.get(chunk_id, {})
        # Cosine similarity
        dot = sum(w * qvec.get(term, 0) for term, w in vector.items())
        qnorm = math.sqrt(sum(v * v for v in qvec.values()))
        vnorm = math.sqrt(sum(w * w for w in vector.values()))
        cosine = dot / (qnorm * vnorm) if qnorm and vnorm else 0.0

        # Score combinado: 70% cosine + 30% BM25 normalizado
        # SQLite BM25 devuelve valores negativos (menor = mejor). Normalizar a [0,1]
        # Usar exp(bm25) para convertir a probabilidad-like, o min-max sobre candidatos
        bm25 = bm25_map.get(rowid, 0.0)
        # Normalizar BM25: exp(bm25) da valores en (0,1] donde mayor = mejor
        import math as _math
        bm25_norm = _math.exp(bm25) if bm25 < 0 else 1.0 / (1.0 + bm25)
        combined = 0.7 * cosine + 0.3 * bm25_norm

        if combined > 0:
            results.append((combined, chunk_row))

    results.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "archivo": row["archivo"],
            "contenido": row["contenido"][:1200],
            "score": round(score, 4),
        }
        for score, row in results[:k]
    ]


def check_sqlite_fresh() -> bool:
    """True si SQLite DB existe y cubre todos los archivos con mtimes vigentes."""
    if not SQLITE_DB.exists():
        return False
    if not MANIFEST.exists():
        return False
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = _files()
    if len(manifest) != len(files):
        return False
    return all(
        manifest.get(str(p.relative_to(KNOWLEDGE_DIR))) == p.stat().st_mtime for p in files
    )


def build_json_index() -> tuple[int, int]:
    """Indice TF-IDF plano en JSON. Devuelve (archivos, chunks)."""
    files = _files()
    manifest: dict = {}
    chunks_meta: list[dict] = []
    docs: list[list[str]] = []
    doc_count = len(files)

    for path in files:
        mtime = path.stat().st_mtime
        manifest[str(path.relative_to(KNOWLEDGE_DIR))] = mtime
        text = path.read_text(encoding="utf-8", errors="replace")
        for chunk in _chunks(text):
            tokens = _tokenize(chunk)
            docs.append(tokens)
            chunks_meta.append(
                {
                    "archivo": f".docs/knowledge/{path.relative_to(KNOWLEDGE_DIR)}",
                    "contenido": chunk,
                    "tokens": tokens,
                }
            )

    df: dict[str, int] = {}
    for tokens in docs:
        for term in set(tokens):
            df[term] = df.get(term, 0) + 1

    def tfidf(tokens: list[str]) -> dict[str, float]:
        tf: dict[str, float] = {}
        for term in tokens:
            tf[term] = tf.get(term, 0) + 1
        total = len(tokens) or 1
        return {
            term: (count / total) * math.log(1 + doc_count / (1 + df.get(term, 0)))
            for term, count in tf.items()
        }

    vectors = [tfidf(tokens) for tokens in docs]
    JSON_INDEX.write_text(
        json.dumps(
            {
                "version": 2,
                "tipo": "json-tfidf",
                "chunks": chunks_meta,
                "vectors": vectors,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    MANIFEST.write_text(json.dumps(manifest), encoding="utf-8")
    return len(files), len(chunks_meta)


def _chunk_id(path: Path, idx: int) -> str:
    """ID unico por chunk usando la ruta relativa (evita colisiones entre
    archivos homonimos en directorios distintos)."""
    return f"{path.relative_to(KNOWLEDGE_DIR)}:{idx}"


def build_chroma_index() -> tuple[int, int]:
    """Indice vectorial ChromaDB + sentence-transformers."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    files = _files()
    model = SentenceTransformer(MODEL_NAME)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection("knowledge", metadata={"hnsw:space": "cosine"})

    texts: list[str] = []
    ids: list[str] = []
    metas: list[dict] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for idx, chunk in enumerate(_chunks(text)):
            texts.append(chunk)
            ids.append(_chunk_id(path, idx))
            metas.append({"archivo": str(path.relative_to(ROOT))})

    if texts:
        embeddings = model.encode(texts).tolist()
        collection.upsert(ids=ids, documents=texts, metadatas=metas, embeddings=embeddings)

    MANIFEST.write_text(
        json.dumps({str(p.relative_to(KNOWLEDGE_DIR)): p.stat().st_mtime for p in files}),
        encoding="utf-8",
    )
    return len(files), len(texts)


def search_json(query: str, k: int = 5) -> list[dict]:
    """Busca sobre index.json con similitud coseno TF-IDF."""
    data = json.loads(JSON_INDEX.read_text(encoding="utf-8"))
    qvec = {term: 1.0 for term in _tokenize(query)}
    if not qvec:
        return []
    results: list[tuple[float, dict]] = []
    for meta, vector in zip(data["chunks"], data["vectors"]):
        score = sum(count * qvec.get(term, 0) for term, count in vector.items())
        if score > 0:
            results.append((score, meta))
    results.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "archivo": meta["archivo"],
            "contenido": meta["contenido"][:1200],
            "score": round(score, 4),
        }
        for score, meta in results[:k]
    ]


def search_chroma(query: str, k: int = 5) -> list[dict]:
    import chromadb
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection("knowledge")
    result = collection.query(query_embeddings=model.encode([query]).tolist(), n_results=k)
    out = []
    for doc, meta, dist in zip(
        result["documents"][0], result["metadatas"][0], result["distances"][0]
    ):
        out.append(
            {
                "archivo": meta.get("archivo", ""),
                "contenido": doc[:1200],
                "score": round(1 - float(dist), 4),
            }
        )
    return out


def index_all(force: bool = False) -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    if not force and MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    files = _files()
    if not files:
        print("index_knowledge: no hay archivos .md en .docs/knowledge/")
        return
    if not force and all(
        manifest.get(str(p.relative_to(KNOWLEDGE_DIR))) == p.stat().st_mtime for p in files
    ):
        print(f"index_knowledge: sin cambios ({len(files)} archivos)")
        return

    if _chroma_available():
        n_files, n_chunks = build_chroma_index()
        print(f"index_knowledge: chroma listo ({n_files} archivos, {n_chunks} chunks)")
    elif _sqlite_available():
        n_files, n_chunks = build_sqlite_index()
        print(f"index_knowledge: SQLite FTS5 listo ({n_files} archivos, {n_chunks} chunks)")
    else:
        n_files, n_chunks = build_json_index()
        print(
            f"index_knowledge: indice JSON TF-IDF ({n_files} archivos, {n_chunks} chunks). "
            "Instala chromadb+sentence-transformers para busqueda vectorial."
        )


def check_fresh() -> bool:
    """True si el indice existe y cubre todos los archivos con mtimes vigentes."""
    if not MANIFEST.exists():
        return False
    if not (JSON_INDEX.exists() or CHROMA_DIR.is_dir() or SQLITE_DB.exists()):
        return False
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = _files()
    if len(manifest) != len(files):
        return False
    return all(
        manifest.get(str(p.relative_to(KNOWLEDGE_DIR))) == p.stat().st_mtime for p in files
    )


def main() -> int:
    if "--check" in sys.argv:
        if check_fresh():
            print("index_knowledge: indice OK y fresco")
            return 0
        print("index_knowledge: indice ausente o desactualizado; ejecuta sin flags para indexar")
        return 1

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) >= 1 and args[0] == "search":
        query = " ".join(args[1:])
        if not query:
            print("uso: python scripts/index_knowledge.py search \"consulta\"")
            return 1
        if CHROMA_DIR.is_dir() and _chroma_available():
            results = search_chroma(query)
        elif SQLITE_DB.exists() and _sqlite_available():
            results = search_sqlite(query)
        elif JSON_INDEX.exists():
            results = search_json(query)
        else:
            print("no hay indice; ejecuta primero: python scripts/index_knowledge.py")
            return 1
        for hit in results:
            print(f"- [{hit['score']}] {hit['archivo']}\n  {hit['contenido'][:200]}")
        return 0

    index_all(force="--all" in sys.argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
