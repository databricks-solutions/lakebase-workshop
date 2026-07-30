# Databricks notebook source
# MAGIC %md
# MAGIC # AI Agent Memory with Lakebase
# MAGIC
# MAGIC **Path:** Agentic Memory &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase feature:** Short-term and long-term memory for AI agents
# MAGIC
# MAGIC Memory lets AI agents remember information from earlier in a conversation
# MAGIC or from previous conversations. Lakebase provides a fully managed Postgres
# MAGIC backend for both types of memory — no extra infrastructure needed.
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. Understand short-term vs. long-term memory
# MAGIC 2. Build **short-term memory** — store and retrieve thread-based conversations
# MAGIC 3. Build **long-term memory** — extract and persist knowledge across sessions
# MAGIC 4. Query both memory layers using SQL
# MAGIC 5. Learn how to connect this to real agent frameworks (LangGraph, OpenAI Agents SDK)
# MAGIC
# MAGIC **Run `00_Setup_Lakebase_Project` first** (the memory tables are created by the seed script in **your PostgreSQL schema**, resolved via `search_path` from `_setup`).
# MAGIC
# MAGIC **Docs:** [AI agent memory](https://docs.databricks.com/aws/en/generative-ai/agent-framework/stateful-agents)
# MAGIC
# MAGIC > ### DIY memory vs. Managed agent memory (Beta)
# MAGIC > Databricks now offers **Managed agent memory** (Beta, announced Jun 23, 2026) — a
# MAGIC > **Unity Catalog-governed** memory service that handles storage and retrieval for you,
# MAGIC > with no schema to design or SQL to write.
# MAGIC >
# MAGIC > This lab teaches the **DIY Lakebase-backed pattern**: you own the schema and the queries.
# MAGIC > Choose it when you need **custom memory schema, fine-grained retrieval logic, or the
# MAGIC > lowest-latency reads/writes** co-located with your operational data. Reach for **Managed
# MAGIC > agent memory** when you want a governed, zero-plumbing default. The two are complementary —
# MAGIC > the concepts here (short-term vs. long-term, upsert, recall) apply to both.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Agent Memory Architecture
# MAGIC
# MAGIC Agents use **two layers** of memory backed by Lakebase:
# MAGIC
# MAGIC | | Short-term memory | Long-term memory |
# MAGIC |---|---|---|
# MAGIC | **What** | Entire conversation threads | Key-value pairs of extracted knowledge |
# MAGIC | **Scope** | Single session (thread ID) | Across all sessions for a user |
# MAGIC | **Stored as** | Ordered messages with roles | Topic → memory key-value pairs |
# MAGIC | **Use case** | Follow-up questions within a session | Personalization, preferences, learned facts |
# MAGIC | **Backed by** | `agent_sessions` + `agent_messages` tables | `agent_memory_store` table |

# COMMAND ----------

# MAGIC %md
# MAGIC ### Architecture Diagram
# MAGIC
# MAGIC The diagram below shows how the two memory layers work together:
# MAGIC
# MAGIC - **Short-term memory** (left) — entire conversations stored in Lakebase,
# MAGIC   keyed by Thread ID. The agent reads these messages to maintain context
# MAGIC   within a session.
# MAGIC - **Long-term memory** (right) — key information extracted from multiple
# MAGIC   conversations and stored as key-value pairs. Agents access both layers
# MAGIC   to provide personalized, context-aware responses.
# MAGIC - Both memory layers are backed by Lakebase tables — the same managed
# MAGIC   Postgres your application already uses.
# MAGIC
# MAGIC ![Agent Memory Architecture](../../docs/images/agent_memory_architecture.png)

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

import uuid, json

conn = get_connection()
print(f"✓ Connected to {PROJECT_ID} / production")
show_app_link("agent", "Agent Memory")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Part 1: Short-Term Memory
# MAGIC
# MAGIC Short-term memory captures context within a **single conversation session**
# MAGIC using thread IDs and message ordering. This is the foundation for multi-turn
# MAGIC chat — the agent can refer back to earlier messages in the same thread.
# MAGIC
# MAGIC The pattern uses two tables:
# MAGIC - **`agent_sessions`** — one row per conversation thread (thread ID, agent config, metadata)
# MAGIC - **`agent_messages`** — ordered messages within each thread (role, content, timestamp)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1.1 Create a Conversation Thread

# COMMAND ----------

THREAD_ID = str(uuid.uuid4())[:16]

with conn.cursor() as cur:
    cur.execute("""
        INSERT INTO agent_sessions (session_id, agent_name, metadata)
        VALUES (%s, %s, %s)
        RETURNING session_id, agent_name, created_at
    """, (THREAD_ID, "workshop-assistant", json.dumps({
        "model": "databricks-meta-llama-3-3-70b-instruct",
        "temperature": 0.7,
        "user": user_email,
        "purpose": "lakebase-workshop-demo"
    })))
    session = cur.fetchone()
conn.commit()
print(f"✓ Thread created: {session['session_id']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1.2 Store a Multi-Turn Conversation
# MAGIC
# MAGIC Each message is stored with its role (`system`, `user`, `assistant`, `tool`)
# MAGIC and a timestamp. The agent reconstructs context by reading messages in order.

# COMMAND ----------

CONVERSATION = [
    ("system", "You are a helpful data engineering assistant for Databricks Lakebase."),
    ("user",   "What is Lakebase?"),
    ("assistant", "Lakebase is a fully managed PostgreSQL database service built into Databricks. "
                  "It provides autoscaling compute, copy-on-write branching, scale-to-zero, "
                  "and tight integration with Unity Catalog."),
    ("user",   "How does branching work?"),
    ("assistant", "Branching creates an instant, isolated copy of your database using copy-on-write "
                  "storage. No data is duplicated until you make changes on the branch. This is ideal "
                  "for dev/test environments, CI pipelines, or safe schema migrations."),
    ("user",   "Can I sync data from Delta Lake?"),
    ("assistant", "Yes! Lakebase supports Reverse ETL through synced tables. You create a Delta table "
                  "with Change Data Feed enabled, then set up a synced table that pushes changes into "
                  "your Lakebase PostgreSQL branch automatically."),
]

with conn.cursor() as cur:
    for role, content in CONVERSATION:
        cur.execute("""
            INSERT INTO agent_messages (session_id, role, content, metadata)
            VALUES (%s, %s, %s, %s)
        """, (THREAD_ID, role, content, json.dumps({"notebook": "Agent_Memory"})))
conn.commit()
print(f"✓ Stored {len(CONVERSATION)} messages in thread {THREAD_ID}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1.3 Retrieve Conversation History
# MAGIC
# MAGIC This is exactly how an agent retrieves context for the next turn —
# MAGIC fetch all messages for the thread, ordered by timestamp.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        SELECT role, content, created_at
        FROM agent_messages
        WHERE session_id = %s
        ORDER BY created_at
    """, (THREAD_ID,))
    print(f"Thread {THREAD_ID} — conversation history:")
    for msg in cur.fetchall():
        preview = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
        print(f"  [{msg['role']}] {preview}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1.4 Checkpoint Pattern
# MAGIC
# MAGIC In production, frameworks like **LangGraph** use checkpointing to save
# MAGIC the full agent state (not just messages) after each step. Lakebase serves
# MAGIC as the checkpoint backend — the `agent-langgraph-advanced` template
# MAGIC demonstrates this pattern with LangGraph's built-in `PostgresSaver`.
# MAGIC
# MAGIC ```python
# MAGIC from langgraph.checkpoint.postgres import PostgresSaver
# MAGIC
# MAGIC checkpointer = PostgresSaver.from_conn_string(connection_string)
# MAGIC graph = builder.compile(checkpointer=checkpointer)
# MAGIC
# MAGIC # Each invocation automatically saves state to Lakebase
# MAGIC result = graph.invoke(input, config={"configurable": {"thread_id": "my-thread"}})
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Part 2: Long-Term Memory
# MAGIC
# MAGIC Long-term memory **extracts key information** from multiple conversations
# MAGIC and stores it as key-value pairs. This allows agents to personalize
# MAGIC interactions based on past preferences and build knowledge about users
# MAGIC that improves responses over time.
# MAGIC
# MAGIC The `agent_memory_store` table stores knowledge as:
# MAGIC - **`user_id`** — whose knowledge this belongs to
# MAGIC - **`topic`** — the key (e.g., "preferred_language", "team", "data_platform")
# MAGIC - **`memory`** — the extracted value

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2.1 Extract and Store Knowledge
# MAGIC
# MAGIC In a real agent, an LLM extracts key facts from conversations
# MAGIC automatically. Here we simulate that extraction — imagine the agent
# MAGIC learned these facts from the conversation above.

# COMMAND ----------

MEMORIES = [
    ("preferred_language", "Python — user asked about Python-based data engineering"),
    ("data_platform", "Databricks — user is actively learning Lakebase and Unity Catalog"),
    ("interests", "Branching workflows, Reverse ETL, schema migrations"),
    ("experience_level", "Intermediate — familiar with Delta Lake, exploring Lakebase"),
    ("team", "Data Engineering — context from questions about pipelines and synced tables"),
]

with conn.cursor() as cur:
    for topic, memory in MEMORIES:
        cur.execute("""
            INSERT INTO agent_memory_store (user_id, topic, memory, metadata)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, topic)
            DO UPDATE SET memory = EXCLUDED.memory, updated_at = CURRENT_TIMESTAMP
        """, (user_email, topic, memory, json.dumps({"source_thread": THREAD_ID})))
conn.commit()
print(f"✓ Stored {len(MEMORIES)} long-term memories for {user_email}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2.2 Retrieve User Knowledge
# MAGIC
# MAGIC Before generating a response, the agent looks up everything it knows
# MAGIC about the current user to personalize the interaction.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        SELECT topic, memory, updated_at
        FROM agent_memory_store
        WHERE user_id = %s
        ORDER BY topic
    """, (user_email,))
    print(f"Long-term memory for {user_email}:")
    for row in cur.fetchall():
        print(f"  {row['topic']}: {row['memory']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2.3 Use Memory to Build a System Prompt
# MAGIC
# MAGIC Long-term memory is typically injected into the system prompt so the
# MAGIC agent has context before the user says anything.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        SELECT topic, memory FROM agent_memory_store
        WHERE user_id = %s ORDER BY topic
    """, (user_email,))
    memories = cur.fetchall()

memory_context = "\n".join(f"- {m['topic']}: {m['memory']}" for m in memories)
system_prompt = f"""You are a helpful data engineering assistant.

Here is what you know about this user from previous conversations:
{memory_context}

Use this context to personalize your responses."""

print("Generated system prompt with long-term memory:\n")
print(system_prompt)

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Part 3: Querying Both Memory Layers
# MAGIC
# MAGIC Since both memory layers are stored in Lakebase (standard Postgres),
# MAGIC you can query them with SQL for analytics, debugging, or auditing.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.1 All Threads for a User

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        SELECT s.session_id, s.agent_name,
               s.metadata->>'model' AS model,
               COUNT(m.message_id) AS message_count,
               s.created_at
        FROM agent_sessions s
        LEFT JOIN agent_messages m ON s.session_id = m.session_id
        WHERE s.metadata->>'user' = %s
        GROUP BY s.session_id, s.agent_name, s.metadata, s.created_at
        ORDER BY s.created_at DESC
    """, (user_email,))
    print(f"Threads for {user_email}:")
    for row in cur.fetchall():
        print(f"  {row['session_id']} | {row['agent_name']} | "
              f"model={row['model']} | msgs={row['message_count']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.2 Memory Store Overview

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        SELECT user_id,
               COUNT(*) AS total_memories,
               MIN(created_at) AS first_memory,
               MAX(updated_at) AS last_updated
        FROM agent_memory_store
        GROUP BY user_id
        ORDER BY last_updated DESC
    """)
    print("Memory store summary:")
    for row in cur.fetchall():
        print(f"  {row['user_id']}: {row['total_memories']} memories "
              f"(last updated: {row['last_updated']})")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Part 4: Production Patterns
# MAGIC
# MAGIC ### Framework Integration
# MAGIC
# MAGIC Databricks provides pre-built app templates that implement both memory
# MAGIC layers with popular agent frameworks:
# MAGIC
# MAGIC | Framework | Template | Memory Types |
# MAGIC |-----------|----------|-------------|
# MAGIC | **LangGraph** | `agent-langgraph-advanced` | Short-term (checkpointing) + Long-term (Lakebase store) |
# MAGIC | **OpenAI Agents SDK** | `agent-openai-advanced` | Short-term (conversation history in Lakebase) |
# MAGIC
# MAGIC ```bash
# MAGIC # Clone a template to get started
# MAGIC git clone https://github.com/databricks/app-templates.git
# MAGIC cd app-templates/agent-langgraph-advanced
# MAGIC ```
# MAGIC
# MAGIC ### Why Lakebase for Agent Memory?
# MAGIC
# MAGIC | Benefit | Details |
# MAGIC |---------|---------|
# MAGIC | **No extra infrastructure** | Same managed Postgres your app already uses |
# MAGIC | **ACID transactions** | Memory updates are atomic — no partial writes |
# MAGIC | **SQL queryable** | Debug, audit, and analyze agent behavior with standard SQL |
# MAGIC | **Branching** | Test memory schemas on a dev branch before touching production |
# MAGIC | **Scale-to-zero** | Dev/test memory stores cost nothing when idle |
# MAGIC
# MAGIC **Docs:** [AI agent memory](https://docs.databricks.com/aws/en/generative-ai/agent-framework/stateful-agents)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Clean Up (Optional)

# COMMAND ----------

# UNCOMMENT TO CLEAN UP:
# with conn.cursor() as cur:
#     cur.execute("DELETE FROM agent_memory_store WHERE user_id = %s", (user_email,))
#     cur.execute("DELETE FROM agent_sessions WHERE session_id = %s", (THREAD_ID,))
# conn.commit()
# print(f"✓ Deleted thread {THREAD_ID} and long-term memories for {user_email}")

# COMMAND ----------

conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's Next?
# MAGIC
# MAGIC Continue to another lab path:
# MAGIC
# MAGIC | Path | Folder | What You'll Learn |
# MAGIC |------|--------|-------------------|
# MAGIC | **Data Operations** | `labs/data-operations/` | CRUD, JSONB queries, array operators, audit triggers, transactions |
# MAGIC | **Reverse ETL** | `labs/reverse-etl/` | Sync Delta Lake tables into Lakebase for low-latency serving |
# MAGIC | **Development Experience** | `labs/development-experience/` | Git-like branching, autoscaling compute, scale-to-zero |
# MAGIC | **Observability** | `labs/observability/` | pg_stat views, index analysis, connection monitoring |
# MAGIC | **Authentication** | `labs/authentication/` | OAuth tokens, two-layer permissions, role grants |
# MAGIC | **Backup & Recovery** | `labs/backup-recovery/` | Point-in-time recovery, branch snapshots, instant restore |
# MAGIC | **Online Feature Store** | `labs/online-feature-store/` | Real-time ML feature serving powered by Lakebase Autoscaling |
# MAGIC | **App Deployment** | `labs/app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |
