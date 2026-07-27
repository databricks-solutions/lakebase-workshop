# Databricks notebook source
# MAGIC %md
# MAGIC # Lakebase Search — Vector, Keyword & Hybrid
# MAGIC
# MAGIC **Path:** Lakebase Search &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase feature:** Lakebase Search *(Beta)* — hybrid vector + keyword search inside Postgres
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. Enable and install the search extensions (`lakebase_vector`, `lakebase_text`)
# MAGIC 2. Build a searchable `search_documents` table with a vector column + a full-text column
# MAGIC 3. Run **vector (semantic)** search with `lakebase_ann` (pgvector-compatible)
# MAGIC 4. Run **keyword (BM25)** search with `lakebase_bm25`
# MAGIC 5. Combine both into a single ranking with **hybrid search (Reciprocal Rank Fusion)**
# MAGIC 6. *(Optional)* Add semantic recall to the Agentic Memory lab's `agent_memory_store`
# MAGIC
# MAGIC **Run `00_Setup_Lakebase_Project` first.** Table references use unqualified names; your schema is set via `search_path` in `_setup`.
# MAGIC
# MAGIC **Docs:** [Lakebase Search](https://docs.databricks.com/aws/en/oltp/projects/lakebase-search) |
# MAGIC [lakebase_vector](https://docs.databricks.com/aws/en/oltp/projects/lakebase-vector) |
# MAGIC [lakebase_text](https://docs.databricks.com/aws/en/oltp/projects/lakebase-text)

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⚠️ Before you run: Lakebase Search is Beta and enablement is irreversible
# MAGIC
# MAGIC Lakebase Search is in **Beta**. Enabling it on a project:
# MAGIC
# MAGIC - **Restarts all computes in the project**, dropping active connections
# MAGIC - Makes the `lakebase_vector` and `lakebase_text` extensions available to install
# MAGIC - **Cannot be turned off once enabled**
# MAGIC
# MAGIC It also requires **Beta access** for your project (a workspace admin enables it from the
# MAGIC **Previews** page; contact your Databricks account team to request it). Requirements: **Postgres 16+**.
# MAGIC
# MAGIC **Enable it once, in the UI:** Lakebase project → **Settings** → **Lakebase Search** → **Enable**.
# MAGIC
# MAGIC > This is your own workshop project, so enabling is your call — but because it restarts compute
# MAGIC > and is permanent, this notebook **detects** whether Search is enabled and skips gracefully if not.

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

conn = get_connection("production")
print("✓ Connected to production branch")


def run(sql, params=None, show=True, label=None):
    """Execute SQL and (optionally) print the returned rows."""
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        conn.commit()
        if cur.description is None:
            return []
        rows = cur.fetchall()
    if show:
        if label:
            print(f"— {label} —")
        for r in rows:
            print(dict(r))
    return rows

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Install the search extensions
# MAGIC
# MAGIC After Lakebase Search is enabled for your project, install the two extensions.
# MAGIC `CASCADE` on `lakebase_vector` also installs `pgvector` as a dependency.

# COMMAND ----------

SEARCH_READY = False
try:
    run("CREATE EXTENSION IF NOT EXISTS lakebase_vector CASCADE;", show=False)  # ANN vector search (+ pgvector)
    run("CREATE EXTENSION IF NOT EXISTS lakebase_text;", show=False)            # BM25 full-text search
    SEARCH_READY = True
    print("✓ lakebase_vector + lakebase_text installed — Search is ready")
except Exception as e:
    print("✗ Could not install the Lakebase Search extensions.")
    print("  This almost always means Lakebase Search isn't enabled for this project yet.")
    print("  Enable it in the UI (Settings → Lakebase Search → Enable) and re-run this cell.")
    print(f"  Underlying error: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Build a searchable table
# MAGIC
# MAGIC We store two things per row: an **`embedding`** vector (for semantic search) and a
# MAGIC **`body_tsv`** `tsvector` (for keyword search).
# MAGIC
# MAGIC > **About the embeddings:** the vectors below are small, hand-written literals so the lab is
# MAGIC > self-contained. In a real application you generate embeddings with a model — on Databricks,
# MAGIC > use **Model Serving** (e.g. `ai_query(...)` in a notebook or Databricks SQL) and insert the
# MAGIC > result into the `VECTOR(n)` column. The column and index dimension `n` must match your model's
# MAGIC > output (commonly 384–1536). See Section 6 for the real-embeddings pattern.

# COMMAND ----------

if SEARCH_READY:
    run("DROP TABLE IF EXISTS search_documents CASCADE;", show=False)
    run("""
        CREATE TABLE search_documents (
            id        SERIAL PRIMARY KEY,
            title     TEXT NOT NULL,
            body      TEXT NOT NULL,
            embedding VECTOR(3),
            body_tsv  TSVECTOR
        );
    """, show=False)

    # Vector index can be created on an empty table (ANN); build it up front.
    run("CREATE INDEX ON search_documents USING lakebase_ann (embedding vector_cosine_ops);", show=False)

    # Insert documents. body_tsv is populated with to_tsvector at insert time.
    run("""
        INSERT INTO search_documents (title, body, embedding, body_tsv) VALUES
          ('Postgres overview',   'Postgres is an open-source relational database.',        '[0.10, 0.20, 0.30]', to_tsvector('english', 'Postgres is an open-source relational database.')),
          ('Vector search guide', 'Vector search finds semantically similar results.',      '[0.40, 0.50, 0.60]', to_tsvector('english', 'Vector search finds semantically similar results.')),
          ('Full-text search',    'BM25 ranking improves keyword search relevance.',        '[0.70, 0.80, 0.90]', to_tsvector('english', 'BM25 ranking improves keyword search relevance.')),
          ('Lakebase database',   'Lakebase is a managed Postgres database on Databricks.', '[0.12, 0.22, 0.34]', to_tsvector('english', 'Lakebase is a managed Postgres database on Databricks.')),
          ('Hybrid retrieval',    'Hybrid search blends semantic and keyword relevance.',   '[0.44, 0.52, 0.63]', to_tsvector('english', 'Hybrid search blends semantic and keyword relevance.'));
    """, show=False)

    # BM25 index must be built AFTER inserting data (it computes corpus statistics at build time).
    run("CREATE INDEX search_documents_body_bm25 ON search_documents USING lakebase_bm25 (body_tsv);", show=False)

    print("✓ search_documents built: 5 rows, ANN + BM25 indexes created")
else:
    print("Skipped — enable Lakebase Search first (see cell above).")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Vector (semantic) search
# MAGIC
# MAGIC Order by the pgvector cosine-distance operator `<=>`. The nearest vectors to the query come first.
# MAGIC (Because we hand-wrote the vectors, "database" and "search" docs cluster into two groups.)

# COMMAND ----------

if SEARCH_READY:
    run("""
        SELECT id, title
        FROM search_documents
        ORDER BY embedding <=> '[0.11, 0.21, 0.32]'
        LIMIT 3;
    """, label="Nearest to a 'database'-like query vector")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Keyword (BM25) search
# MAGIC
# MAGIC The `<@>` operator returns a **negative BM25 score**, so order **ascending** for the most
# MAGIC relevant rows first. `to_bm25query` builds the query object against the BM25 index.

# COMMAND ----------

if SEARCH_READY:
    run("""
        SELECT id, title,
               body_tsv <@> to_bm25query(to_tsvector('english', 'search'), 'search_documents_body_bm25') AS score
        FROM search_documents
        ORDER BY score
        LIMIT 3;
    """, label="Top keyword matches for 'search'")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Hybrid search (Reciprocal Rank Fusion)
# MAGIC
# MAGIC Run each search independently, take the top candidates from each, then fuse the two ranked
# MAGIC lists with **RRF**: `score = Σ 1 / (k + rank)`. Rows that rank well in *either* list bubble up.
# MAGIC The constant `k = 60` dampens low-ranked results; `id` breaks ties for stable pagination.

# COMMAND ----------

if SEARCH_READY:
    run("""
        WITH vector_ranked AS (
          SELECT id, RANK() OVER (ORDER BY dist) AS rank
          FROM (
            SELECT id, embedding <=> '[0.11, 0.21, 0.32]' AS dist
            FROM search_documents
            ORDER BY dist
            LIMIT 40
          ) v
        ),
        keyword_ranked AS (
          SELECT id, RANK() OVER (ORDER BY score) AS rank
          FROM (
            SELECT id, body_tsv <@> to_bm25query(to_tsvector('english', 'database search'), 'search_documents_body_bm25') AS score
            FROM search_documents
            ORDER BY score
            LIMIT 40
          ) k
        )
        SELECT d.id, d.title,
               COALESCE(1.0 / (60 + v.rank), 0) + COALESCE(1.0 / (60 + k.rank), 0) AS rrf_score
        FROM search_documents d
        LEFT JOIN vector_ranked v ON d.id = v.id
        LEFT JOIN keyword_ranked k ON d.id = k.id
        WHERE v.id IS NOT NULL OR k.id IS NOT NULL
        ORDER BY rrf_score DESC, d.id
        LIMIT 5;
    """, label="Hybrid RRF ranking")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Real embeddings with Model Serving (pattern)
# MAGIC
# MAGIC In production you don't hand-write vectors — you embed text with a model. On Databricks you can
# MAGIC call an embedding endpoint with `ai_query` from Databricks SQL / a Spark notebook, then write the
# MAGIC vectors into Lakebase (the `VECTOR(n)` dimension must match the model's output). Sketch:
# MAGIC
# MAGIC ```python
# MAGIC # 1) Embed text in the lakehouse with a served embedding model (e.g. gte-large-en → 1024 dims)
# MAGIC #    SELECT id, ai_query('databricks-gte-large-en', body) AS embedding FROM source_docs
# MAGIC #
# MAGIC # 2) Create the Lakebase column/index at that dimension:
# MAGIC #    ALTER TABLE search_documents ADD COLUMN embedding_1024 VECTOR(1024);
# MAGIC #    CREATE INDEX ON search_documents USING lakebase_ann (embedding_1024 vector_cosine_ops);
# MAGIC #
# MAGIC # 3) Embed the *query* with the SAME model, then run the same <=> / RRF queries above.
# MAGIC ```
# MAGIC
# MAGIC Use the operator class that matches how your embeddings were trained:
# MAGIC `vector_cosine_ops` (normalized embeddings, most common), `vector_l2_ops` (Euclidean), or
# MAGIC `vector_ip_ops` (inner product / pre-normalized unit vectors).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. (Optional) Semantic recall over agent memory
# MAGIC
# MAGIC The **Agentic Memory** lab stores long-term memories in `agent_memory_store`. With Lakebase
# MAGIC Search you can add an `embedding` column there and retrieve memories by *meaning* instead of by
# MAGIC exact `topic` — the retrieval half of a RAG loop, co-located with your operational data.
# MAGIC
# MAGIC ```python
# MAGIC # ALTER TABLE agent_memory_store ADD COLUMN embedding VECTOR(1024);
# MAGIC # CREATE INDEX ON agent_memory_store USING lakebase_ann (embedding vector_cosine_ops);
# MAGIC # -- Backfill embeddings for the `memory` column (via Model Serving), then:
# MAGIC # SELECT topic, memory
# MAGIC # FROM agent_memory_store
# MAGIC # WHERE user_id = %s
# MAGIC # ORDER BY embedding <=> %s   -- the embedded user query
# MAGIC # LIMIT 5;
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Clean Up (Optional)

# COMMAND ----------

# UNCOMMENT TO CLEAN UP:
# if SEARCH_READY:
#     run("DROP TABLE IF EXISTS search_documents CASCADE;", show=False)
#     print("✓ Dropped search_documents")
# conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's Next?
# MAGIC
# MAGIC | Path | Folder | What You'll Learn |
# MAGIC |------|--------|-------------------|
# MAGIC | **Agentic Memory** | `labs/agentic-memory/` | Short/long-term AI agent memory — pair it with Section 7 above |
# MAGIC | **Data API** | `labs/data-api/` | Expose your searchable tables over REST |
# MAGIC | **App Deployment** | `labs/app-deployment/` | Put search behind a full-stack app (capstone) |
