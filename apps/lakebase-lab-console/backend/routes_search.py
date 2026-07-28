"""Lakebase Search routes — guarded interactive helper.

Lakebase Search (Beta) adds hybrid vector + keyword search inside Postgres via
the `lakebase_vector` and `lakebase_text` extensions. Enabling Search is
irreversible and restarts compute, so these routes NEVER run `CREATE EXTENSION`.
They only:

  - detect whether the extensions are installed (status),
  - build/seed a small demo table + ANN/BM25 indexes when Search is ready (seed),
  - run vector / keyword / hybrid (RRF) queries against the demo table (query).

When Search isn't enabled, the frontend renders an informational fallback.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .db import execute_query, execute_write, get_schema
from .user_context import UserContext, get_current_user

router = APIRouter(prefix="/api/search", tags=["search"])

_DEFAULT_QUERY_VECTOR = "[0.11, 0.21, 0.32]"
_BM25_INDEX = "search_documents_body_bm25"


@router.get("/status")
def status(user: UserContext = Depends(get_current_user)):
    """Detect whether Lakebase Search is enabled and the demo table exists."""
    extensions: list[str] = []
    try:
        rows = execute_query(
            user,
            "SELECT extname FROM pg_extension WHERE extname IN ('lakebase_vector', 'lakebase_text', 'vector')",
        )
        extensions = [r["extname"] for r in rows]
    except Exception:
        pass

    ready = "lakebase_vector" in extensions and "lakebase_text" in extensions

    table_exists = False
    if ready:
        try:
            table_exists = bool(execute_query(
                user,
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = %s AND table_name = 'search_documents'
                """,
                (get_schema(user),),
            ))
        except Exception:
            pass

    return {"ready": ready, "extensions": extensions, "table_exists": table_exists}


@router.post("/seed")
def seed(user: UserContext = Depends(get_current_user)):
    """Build + seed the search_documents demo table (only if Search is enabled)."""
    ext = execute_query(
        user,
        "SELECT extname FROM pg_extension WHERE extname IN ('lakebase_vector', 'lakebase_text')",
    )
    names = {r["extname"] for r in ext}
    if not {"lakebase_vector", "lakebase_text"}.issubset(names):
        raise HTTPException(
            400,
            "Lakebase Search isn't enabled for this project. Enable it in the UI "
            "(Settings -> Lakebase Search) and install the extensions via the "
            "labs/lakebase-search/ notebook first. This app never enables Search itself.",
        )

    statements = [
        "DROP TABLE IF EXISTS search_documents CASCADE;",
        """
        CREATE TABLE search_documents (
            id        SERIAL PRIMARY KEY,
            title     TEXT NOT NULL,
            body      TEXT NOT NULL,
            embedding VECTOR(3),
            body_tsv  TSVECTOR
        );
        """,
        "CREATE INDEX ON search_documents USING lakebase_ann (embedding vector_cosine_ops);",
        """
        INSERT INTO search_documents (title, body, embedding, body_tsv) VALUES
          ('Postgres overview',   'Postgres is an open-source relational database.',        '[0.10, 0.20, 0.30]', to_tsvector('english', 'Postgres is an open-source relational database.')),
          ('Vector search guide', 'Vector search finds semantically similar results.',      '[0.40, 0.50, 0.60]', to_tsvector('english', 'Vector search finds semantically similar results.')),
          ('Full-text search',    'BM25 ranking improves keyword search relevance.',        '[0.70, 0.80, 0.90]', to_tsvector('english', 'BM25 ranking improves keyword search relevance.')),
          ('Lakebase database',   'Lakebase is a managed Postgres database on Databricks.', '[0.12, 0.22, 0.34]', to_tsvector('english', 'Lakebase is a managed Postgres database on Databricks.')),
          ('Hybrid retrieval',    'Hybrid search blends semantic and keyword relevance.',   '[0.44, 0.52, 0.63]', to_tsvector('english', 'Hybrid search blends semantic and keyword relevance.'));
        """,
        f"CREATE INDEX {_BM25_INDEX} ON search_documents USING lakebase_bm25 (body_tsv);",
    ]
    try:
        for stmt in statements:
            execute_write(user, stmt)
    except Exception as e:
        raise HTTPException(400, f"Failed to seed search_documents: {e}")

    return {"ok": True, "rows": 5, "message": "search_documents built with ANN + BM25 indexes"}


class QueryRequest(BaseModel):
    mode: str = "hybrid"          # 'vector' | 'keyword' | 'hybrid'
    query: str = "database search"
    query_vector: str | None = None
    limit: int = 5


@router.post("/query")
def query(req: QueryRequest, user: UserContext = Depends(get_current_user)):
    """Run a vector, keyword, or hybrid (RRF) search over the demo table."""
    qvec = (req.query_vector or _DEFAULT_QUERY_VECTOR).strip()
    limit = max(1, min(req.limit, 20))
    mode = req.mode.lower()

    try:
        if mode == "vector":
            rows = execute_query(
                user,
                """
                SELECT id, title, (embedding <=> %s::vector) AS distance
                FROM search_documents
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (qvec, qvec, limit),
            )
        elif mode == "keyword":
            rows = execute_query(
                user,
                f"""
                SELECT id, title,
                       body_tsv <@> to_bm25query(to_tsvector('english', %s), '{_BM25_INDEX}') AS score
                FROM search_documents
                ORDER BY score
                LIMIT %s
                """,
                (req.query, limit),
            )
        else:  # hybrid (Reciprocal Rank Fusion)
            rows = execute_query(
                user,
                f"""
                WITH vector_ranked AS (
                  SELECT id, RANK() OVER (ORDER BY dist) AS rank
                  FROM (
                    SELECT id, embedding <=> %s::vector AS dist
                    FROM search_documents ORDER BY dist LIMIT 40
                  ) v
                ),
                keyword_ranked AS (
                  SELECT id, RANK() OVER (ORDER BY score) AS rank
                  FROM (
                    SELECT id, body_tsv <@> to_bm25query(to_tsvector('english', %s), '{_BM25_INDEX}') AS score
                    FROM search_documents ORDER BY score LIMIT 40
                  ) k
                )
                SELECT d.id, d.title,
                       COALESCE(1.0 / (60 + v.rank), 0) + COALESCE(1.0 / (60 + k.rank), 0) AS rrf_score
                FROM search_documents d
                LEFT JOIN vector_ranked v ON d.id = v.id
                LEFT JOIN keyword_ranked k ON d.id = k.id
                WHERE v.id IS NOT NULL OR k.id IS NOT NULL
                ORDER BY rrf_score DESC, d.id
                LIMIT %s
                """,
                (qvec, req.query, limit),
            )
    except Exception as e:
        raise HTTPException(400, f"Search query failed (is search_documents seeded?): {e}")

    return {"mode": mode, "results": rows}
