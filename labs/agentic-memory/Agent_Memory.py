# Databricks notebook source
# MAGIC %md
# MAGIC # Managed Agent Memory: Sessions, Memory, and Memory Pipelines
# MAGIC
# MAGIC **Path:** Agentic Memory &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project` + the **Agent Memory Sessions** preview (see below)
# MAGIC
# MAGIC **Lakebase feature:** Managed agent sessions and agent memory (Beta), backed by Lakebase
# MAGIC
# MAGIC An agent keeps two kinds of state: the **interaction it's handling now**, and **durable
# MAGIC facts** it carries between conversations. Databricks provides a managed store for each. Both
# MAGIC are backed by Lakebase and work with agents built on any framework.
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. **Agent sessions:** store and replay one conversation (short-term state).
# MAGIC 2. **Agent memory:** save facts and recall them with natural-language search (long-term state).
# MAGIC 3. **Memory pipelines:** distill the conversation into memory and see how a run changes entries.
# MAGIC 4. **Governance:** store permissions, `actor_id` scoping, and access for the Lab Console app.
# MAGIC 5. **Reference:** the self-managed Lakebase memory pattern that earlier versions of this lab taught.
# MAGIC
# MAGIC **Docs:** [Agent memory and sessions](https://docs.databricks.com/aws/en/agents/custom-agents/stateful-agents) ·
# MAGIC [Agent sessions](https://docs.databricks.com/aws/en/agents/agent-memory/managed-sessions) ·
# MAGIC [Agent memory](https://docs.databricks.com/aws/en/agents/agent-memory/managed-memory) ·
# MAGIC [Memory pipelines](https://docs.databricks.com/aws/en/agents/agent-memory/memory-pipelines) ·
# MAGIC [Store permissions](https://docs.databricks.com/aws/en/agents/agent-memory/store-permissions)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Prerequisites
# MAGIC
# MAGIC | Requirement | Details |
# MAGIC |---|---|
# MAGIC | **Agent Memory Sessions preview** | A **workspace admin** must enable **Agent Memory Sessions** on the workspace **Previews** page. Without it, every call below fails. |
# MAGIC | **`databricks-agentbricks` ≥ 0.8.0** | The AgentKit SDK (`databricks_agentkit`). Installed by the next cell. Python 3.10+. |
# MAGIC | **Model access (Part 3)** | Permission to query the pipeline's distillation model (`PIPELINE_MODEL` below). Without it, pipeline runs fail. |
# MAGIC | **Store quota** | A workspace can hold up to **50 memory stores**. This lab creates one memory store and one session store per participant, so run the cleanup cell when you're done. |
# MAGIC | **`00_Setup_Lakebase_Project`** | Provides the shared `_setup` helpers (your identity, store names, and the Lab Console link). |
# MAGIC
# MAGIC Billing during the preview: you pay for the Lakebase instance that backs the stores; sessions and memory carry no additional charge.

# COMMAND ----------

# MAGIC %md
# MAGIC ## How it fits together
# MAGIC
# MAGIC - **Agent sessions** store the state of **one interaction**, usually the conversation
# MAGIC   history. The agent reads the session at the start of a turn and appends to it as it goes.
# MAGIC - **Agent memory** stores **durable facts, preferences, and decisions** that the agent recalls
# MAGIC   in later conversations.
# MAGIC - A **memory pipeline** reads conversations from a session store, distills durable facts,
# MAGIC   and writes them to a memory store, so your agent doesn't need memory-writing tools.
# MAGIC
# MAGIC ![Agent memory and sessions overview](../../docs/images/agent_memory_overview.png)
# MAGIC
# MAGIC | | Agent sessions | Agent memory |
# MAGIC |---|---|---|
# MAGIC | **Holds** | One interaction's transcript (ordered items) | Durable facts as entries at filesystem-like paths |
# MAGIC | **Scope** | A single session | A subject (`actor_id`), across all conversations |
# MAGIC | **Read by** | Replaying items in order | `list` (browse) and `search` (natural-language recall) |
# MAGIC | **Written by** | `append_items` each turn | Your agent (`put`) or a **memory pipeline** |
# MAGIC
# MAGIC Use both for most agents. Use sessions alone when you only need in-interaction state, and
# MAGIC memory alone when your framework already manages session state. The stores are independent:
# MAGIC deleting a session, or a whole session store, doesn't delete saved memory.

# COMMAND ----------

# MAGIC %pip install "databricks-agentbricks>=0.8.0" "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "protobuf>=5.29.5,<6" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

import json, time, uuid
from databricks_agentkit import AgentKitClient

client = AgentKitClient(w)  # `w` (WorkspaceClient) and `user_email` come from _setup

# Each participant gets their own stores (names derived in _setup from your email).
# Your email is the actor_id: whose memory/session it is.
ACTOR_ID = user_email
print(f"✓ AgentKit client ready for {ACTOR_ID}")
print(f"  session store: {SESSION_STORE_ID}")
print(f"  memory store:  {MEMORY_STORE_ID}")
show_app_link("agent", "Agent Memory")

# COMMAND ----------

def _get_or_create(stores, store_id, description):
    """Open a store, creating it only if it doesn't exist. Other errors (auth, preview off) surface as-is."""
    try:
        return stores.get(store_id)
    except Exception as e:
        if getattr(e, "error_code", None) not in ("RESOURCE_DOES_NOT_EXIST", "NOT_FOUND"):
            raise
    try:
        return stores.create(store_id, description=description)
    except Exception as e:
        if getattr(e, "error_code", None) == "ALREADY_EXISTS":
            raise RuntimeError(
                f"Store {store_id!r} exists but you can't open it; it likely belongs to another user "
                "whose email maps to the same name. Ask the facilitator to rename or delete it."
            ) from e
        raise


def get_or_create_session_store(store_id):
    """Open the session store, creating it on first run."""
    return _get_or_create(client.session_stores, store_id, f"Lakebase workshop sessions for {user_email}")


def get_or_create_memory_store(store_id):
    """Open the memory store, creating it on first run. Creating one provisions its backing storage."""
    return _get_or_create(client.memory_stores, store_id, f"Lakebase workshop memory for {user_email}")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Part 1: Agent Sessions (short-term)
# MAGIC
# MAGIC A **session store** is a workspace-scoped container for sessions. A **session** is one
# MAGIC interaction, such as a conversation thread, owned by an `actor_id`. A **session item** is one
# MAGIC immutable, JSON-compatible entry in the session's history. The service assigns each item's
# MAGIC `item_id` and `create_time` and doesn't validate the contents, so any framework can store its
# MAGIC own state shape.
# MAGIC
# MAGIC ![Agent sessions resource hierarchy](../../docs/images/agent_sessions_hierarchy.png)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1.1 Create the session store and a session

# COMMAND ----------

session_store = get_or_create_session_store(SESSION_STORE_ID)
print(f"✓ Session store ready: {session_store.name}")

THREAD_ID = f"thread-{uuid.uuid4().hex[:12]}"
session = session_store.add(
    actor_id=ACTOR_ID,
    session_id=THREAD_ID,  # optional; the service generates one if omitted
    metadata={"agent": "workshop-assistant", "purpose": "lakebase-workshop-demo"},
)
print(f"✓ Thread created: {session.session_id} (actor {session.actor_id})")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1.2 Append a multi-turn conversation
# MAGIC
# MAGIC Each turn is one session item. This lab uses the message shape from the docs' examples:
# MAGIC `{"type": "message", "role": "user" | "assistant", "content": "<text>"}`. The user mentions
# MAGIC a few facts about themselves, which the memory pipeline picks up in Part 3.

# COMMAND ----------

CONVERSATION = [
    ("user", "Hi! I'm on the data engineering team and I mostly write Python. What is Lakebase?"),
    ("assistant", "Lakebase is a fully managed Postgres service built into Databricks, with autoscaling "
                  "compute, copy-on-write branching, scale-to-zero, and Unity Catalog integration."),
    ("user", "How does branching work? We need safe schema migrations for our pipelines."),
    ("assistant", "A branch is an instant, isolated copy-on-write copy of your database. Test the "
                  "migration on a branch, then apply it to production."),
    ("user", "Can I sync data from Delta Lake? Also, please keep answers short — I prefer concise "
             "answers with code samples."),
    ("assistant", "Yes — synced tables push Delta changes into Lakebase automatically. Noted: concise "
                  "answers with code."),
    ("user", "Great. I'm in Boston, so Eastern time works for any follow-ups."),
]

items = session.append_items(
    [{"type": "message", "role": role, "content": content} for role, content in CONVERSATION]
)
print(f"✓ Stored {len(items)} messages in thread {THREAD_ID}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1.3 Replay the conversation
# MAGIC
# MAGIC An agent replays the session to rebuild context for the next turn. `list_items` returns
# MAGIC newest first and pages automatically. Pass `order_by="create_time asc"` to replay in order.

# COMMAND ----------

history = [item.data for item in session_store.get(THREAD_ID).list_items(order_by="create_time asc")]
print(f"Thread {THREAD_ID} — {len(history)} items:")
for msg in history:
    text = msg["content"]
    print(f"  [{msg['role']}] {text[:100]}{'...' if len(text) > 100 else ''}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1.4 Other session operations
# MAGIC
# MAGIC | Operation | Call | Use |
# MAGIC |---|---|---|
# MAGIC | List sessions | `session_store.list()` | Show a user's recent threads |
# MAGIC | Undo last turn | `session.pop_item()` | Retry or regenerate a response |
# MAGIC | Clear history | `session.clear_items()` | Reset a thread |
# MAGIC | Fork | `session.fork(actor_id=..., up_to_item_id=...)` | Branch a conversation into an independent copy |
# MAGIC | Sub-agents | `session_store.add(..., parent_session_id=...)` | Link a sub-agent conversation to its parent |
# MAGIC | Delete | `session.delete()` | Also deletes child sessions and their items |
# MAGIC
# MAGIC For the OpenAI Agents SDK and LangGraph, `databricks-agentbricks` provides
# MAGIC `databricks_agentkit.openai.session_store(...)` and
# MAGIC `databricks_agentkit.langgraph.checkpointer(...)`, which persist sessions for you.

# COMMAND ----------

print(f"Sessions in {SESSION_STORE_ID}:")
for s in session_store.list():
    print(f"  {s.session_id} | actor={s.actor_id} | metadata={s.metadata}")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Part 2: Agent Memory (long-term)
# MAGIC
# MAGIC A **memory store** is a workspace-scoped container for an agent's memories. A **memory entry**
# MAGIC is free-form text (`content`) with a short `description` used for retrieval, identified by:
# MAGIC
# MAGIC - **`actor_id`** (required): whose memory it is.
# MAGIC - **`session_id`** (optional): leave unset for memory that applies across sessions.
# MAGIC - **`path`** (required): a filesystem-like key, such as `/preferences/response-style.md`.
# MAGIC
# MAGIC The same path under two sessions, or under a session and under none, holds two separate
# MAGIC entries. Your agent writes entries directly, or a memory pipeline distills them from
# MAGIC sessions (Part 3).
# MAGIC
# MAGIC ![Agent memory resource hierarchy](../../docs/images/agent_memory_hierarchy.png)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2.1 Save durable facts with `put()`
# MAGIC
# MAGIC `put()` creates the entry at `(actor_id, session_id, path)` or replaces its content, so
# MAGIC re-running this cell doesn't create duplicates. `add()` fails with `ALREADY_EXISTS` if the
# MAGIC entry exists, and `put(..., append=True)` adds new lines instead of replacing.

# COMMAND ----------

memory_store = get_or_create_memory_store(MEMORY_STORE_ID)
print(f"✓ Memory store ready: {memory_store.name}")

MEMORIES = [
    ("/preferences/preferred-language.md", "Prefers Python for data engineering work.", "Preferred programming language"),
    ("/preferences/data-platform.md", "Uses Databricks; actively learning Lakebase and Unity Catalog.", "Data platform"),
    ("/preferences/interests.md", "Interested in branching workflows, Reverse ETL, and schema migrations.", "Technical interests"),
    ("/preferences/experience-level.md", "Intermediate: familiar with Delta Lake, new to Lakebase.", "Experience level"),
    ("/preferences/team.md", "Works on a data engineering team that builds pipelines and synced tables.", "Team"),
]

for path, content, description in MEMORIES:
    memory_store.put(actor_id=ACTOR_ID, path=path, content=content, description=description)
print(f"✓ Stored {len(MEMORIES)} long-term memories for {ACTOR_ID}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2.2 Browse with `list()`
# MAGIC
# MAGIC `list()` returns one actor's entries. It can filter by `path_prefix`, an exact `path`, or
# MAGIC `session_id`.

# COMMAND ----------

def show_memories(title):
    entries = sorted(memory_store.list(actor_id=ACTOR_ID), key=lambda m: m.path)
    print(f"{title} — {len(entries)} entries for {ACTOR_ID}:")
    for m in entries:
        print(f"  {m.path}: {(m.content or '').replace(chr(10), ' | ')}")
    return {m.path: m.content for m in entries}

before_pipeline = show_memories("Memory store")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2.3 Recall with `search()` and build a system prompt
# MAGIC
# MAGIC `search()` takes a natural-language query and returns one actor's entries ranked by
# MAGIC relevance, combining keyword (BM25) and semantic matching. It returns up to 100 entries and
# MAGIC doesn't paginate. The cell below recalls facts for a question and adds them to a system prompt.

# COMMAND ----------

user_message = "Which language should the code samples use?"
results = memory_store.search(actor_id=ACTOR_ID, query=user_message, limit=3)
print(f"Top {len(results)} memories for: {user_message!r}")
for r in results:
    print(f"  score={r.score:.4f}  {r.memory.path}: {r.memory.content}")

facts = "\n".join(f"- {r.memory.content}" for r in results)
system_prompt = f"""You are a helpful data engineering assistant.

Relevant facts about this user from previous conversations:
{facts}

Use these facts to personalize your response."""
print("\nGenerated system prompt:\n")
print(system_prompt)

# COMMAND ----------

# MAGIC %md
# MAGIC To let an agent manage its own memory, `memory_tools(ACTOR_ID, store=MEMORY_STORE_ID)` from
# MAGIC `databricks_agentkit.openai` or `databricks_agentkit.langgraph` returns four tools bound to
# MAGIC one actor: `recall`, `remember`, `forget`, and `list_memories`. Part 3 shows the other
# MAGIC option, where a pipeline writes memory for you.

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Part 3: Memory Pipelines
# MAGIC
# MAGIC A **memory pipeline** builds long-term memory from past conversations. It reads a
# MAGIC **session store** and writes to a **memory store** under the same `actor_id` as the sessions.
# MAGIC
# MAGIC For each actor, a run reads the sessions added since that actor's last successful run, uses
# MAGIC an LLM to extract durable facts, and merges them into topic-based entries. It then reorganizes
# MAGIC the actor's memory, merging entries that overlap and splitting entries that grow too large. A
# MAGIC run can rewrite, merge, split, or delete any of the actor's entries, **including the ones you
# MAGIC wrote with `put()` in Part 2**.
# MAGIC
# MAGIC | Trigger | Behavior |
# MAGIC |---|---|
# MAGIC | **Manual** (default) | You start each run. This lab uses it. |
# MAGIC | **Scheduled** | About every 24 hours; pause and resume are supported |
# MAGIC | **Always-on** | Runs for an actor when a session has 10+ new items, or 1+ new item and 30 minutes of inactivity |
# MAGIC
# MAGIC Constraints:
# MAGIC - One pipeline per session store and memory store pair.
# MAGIC - One run at a time. Starting a run while another is in progress fails with `ABORTED`.
# MAGIC - A run processes only actors that have sessions, and only items about 60 seconds old or older.
# MAGIC - Runs use the identity that **created** the pipeline.
# MAGIC - Deleting a pipeline keeps the entries it already wrote.
# MAGIC
# MAGIC Memory pipelines aren't Lakeflow pipelines. You manage them with the Agent Bricks CLI or the
# MAGIC REST API (`/api/2.0/agents/memory-pipelines`); this notebook calls the REST API.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.1 Create the pipeline
# MAGIC
# MAGIC `PIPELINE_MODEL` is the distillation model, which the pipeline calls through Unity Gateway.
# MAGIC You can use any model you have permission to query. In testing for this workshop,
# MAGIC `system.ai.gpt-5-4-mini` worked, and a run with `system.ai.claude-sonnet-5-5` failed with
# MAGIC "Structured output is not supported". If your workspace doesn't serve the default, pick
# MAGIC another chat model from **Serving**. Re-running this cell updates an existing pipeline.

# COMMAND ----------

PIPELINE_MODEL = "system.ai.gpt-5-4-mini"
PIPELINE_INSTRUCTIONS = (
    "Keep durable user preferences, profile facts, and working style. "
    "Organize entries by topic under /preferences/. Ignore one-off troubleshooting steps."
)
AGENTS_API = "/api/2.0/agents"


def find_pipeline():
    """Return the pipeline for this store pair, if one already exists (only one is allowed)."""
    token = None
    while True:
        resp = w.api_client.do("GET", f"{AGENTS_API}/memory-pipelines",
                               query={"page_token": token} if token else None)
        for p in resp.get("memory_pipelines", []):
            if p.get("session_store") == f"session-stores/{SESSION_STORE_ID}" and \
               p.get("memory_store") == f"memory-stores/{MEMORY_STORE_ID}":
                return p
        token = resp.get("next_page_token")
        if not token:
            return None


pipeline = find_pipeline()
if pipeline is None:
    pipeline = w.api_client.do("POST", f"{AGENTS_API}/memory-pipelines", body={
        "session_store": f"session-stores/{SESSION_STORE_ID}",
        "memory_store": f"memory-stores/{MEMORY_STORE_ID}",
        "dreamer_policy": {"model": PIPELINE_MODEL, "instructions": PIPELINE_INSTRUCTIONS},
    })
else:
    # Re-running after editing PIPELINE_MODEL / PIPELINE_INSTRUCTIONS updates the existing pipeline.
    current = pipeline.get("dreamer_policy", {})
    changes = {k: v for k, v in (("model", PIPELINE_MODEL), ("instructions", PIPELINE_INSTRUCTIONS))
               if current.get(k) != v}
    if changes:
        pipeline = w.api_client.do("PATCH", f"{AGENTS_API}/{pipeline['name']}",
                                   query={"update_mask": ",".join(f"dreamer_policy.{k}" for k in changes)},
                                   body={"name": pipeline["name"], "dreamer_policy": changes})
        print(f"  updated existing pipeline: {', '.join(changes)}")
PIPELINE_NAME = pipeline["name"]
policy = pipeline.get("dreamer_policy", {})
print(f"✓ Memory pipeline ready: {PIPELINE_NAME}")
print(f"  trigger={policy.get('trigger')} model={policy.get('model')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.2 Run it and wait
# MAGIC
# MAGIC In testing, a run took about two minutes. The cell waits until the conversation items are
# MAGIC old enough to be picked up, starts a run, and polls its `state` until it leaves `RUNNING` for
# MAGIC `SUCCEEDED`, `FAILED`, or `CANCELLED`. If a run is already in progress, the cell waits on it.

# COMMAND ----------

last_item_time = max((i.create_time.timestamp() for i in items if i.create_time), default=time.time())
wait_s = 75 - (time.time() - last_item_time)
if wait_s > 0:
    print(f"Waiting {wait_s:.0f}s for the session items to age past ~60s ...")
    time.sleep(wait_s)

try:
    run = w.api_client.do("POST", f"{AGENTS_API}/{PIPELINE_NAME}/run", body={})
    print(f"Run started: {run['name']}")
except Exception as e:
    if getattr(e, "error_code", None) != "ABORTED":
        raise
    # A run is already in progress (e.g. this cell was re-run): wait on that one instead.
    runs = w.api_client.do("GET", f"{AGENTS_API}/{PIPELINE_NAME}/runs").get("pipeline_runs", [])
    active = sorted((r for r in runs if r.get("state") == "RUNNING"),
                    key=lambda r: str(r.get("create_time") or ""), reverse=True)
    if not active:
        raise
    run = active[0]
    print(f"A run is already in progress; waiting on it: {run['name']}")

deadline = time.time() + 15 * 60
while True:
    run = w.api_client.do("GET", f"{AGENTS_API}/{run['name']}")
    if run.get("state") in ("SUCCEEDED", "FAILED", "CANCELLED") or time.time() > deadline:
        break
    time.sleep(15)

stats = run.get("stats", {})
print(f"Run state: {run.get('state')}")
print(f"  sessions_read={stats.get('sessions_read', 0)} entries_added={stats.get('entries_added', 0)} "
      f"entries_updated={stats.get('entries_updated', 0)} entries_deleted={stats.get('entries_deleted', 0)}")
if run.get("state") == "SUCCEEDED":
    print("✓ Memory pipeline run succeeded")
else:
    # The run's own error is often generic; the failing task's message lives on the backing job run.
    print(f"✗ Memory pipeline run did not succeed: {json.dumps(run)[:800]}")
    print("  Check PIPELINE_MODEL and your permission to query it. The failing task's error is on the job run.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.3 See what the pipeline distilled and merged
# MAGIC
# MAGIC Compare the store with the Part 2 snapshot. Look for **new** facts from the conversation
# MAGIC (response style, time zone) and **merged** entries: overlapping facts, such as language and
# MAGIC team, may be folded into one entry and the others **deleted**. The result depends on the
# MAGIC model and can differ between runs.

# COMMAND ----------

after_pipeline = show_memories("After the pipeline")

added = sorted(set(after_pipeline) - set(before_pipeline))
removed = sorted(set(before_pipeline) - set(after_pipeline))
changed = sorted(p for p in set(before_pipeline) & set(after_pipeline) if before_pipeline[p] != after_pipeline[p])
print(f"\nAdded:   {added or '—'}")
print(f"Merged away (deleted): {removed or '—'}")
print(f"Updated: {changed or '—'}")

print("\nRecall after the pipeline:")
for r in memory_store.search(actor_id=ACTOR_ID, query="How should answers be formatted?", limit=3):
    print(f"  {r.memory.path}: {(r.memory.content or '').replace(chr(10), ' | ')[:160]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.4 Switch the trigger (optional)
# MAGIC
# MAGIC To run the pipeline automatically, `PATCH` `dreamer_policy.trigger` to `SCHEDULED` (about
# MAGIC every 24 hours) or `ALWAYS_ON`. `MANUAL_ONLY` stops automatic runs. The Agent Bricks CLI
# MAGIC equivalents are `agentbricks memory pipeline pause <id>` and `resume <id>`.

# COMMAND ----------

# UNCOMMENT TO RUN DAILY:
# w.api_client.do("PATCH", f"{AGENTS_API}/{PIPELINE_NAME}",
#                 query={"update_mask": "dreamer_policy.trigger"},
#                 body={"name": PIPELINE_NAME, "dreamer_policy": {"trigger": "SCHEDULED"}})

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Part 4: Governance and Access
# MAGIC
# MAGIC **The store is the security boundary.** `actor_id` separates memories but isn't access
# MAGIC control: a principal with access to a store can read every actor's entries. For strict
# MAGIC isolation, use a separate store per tenant or per user.
# MAGIC
# MAGIC | Scope | `actor_id` value | Example |
# MAGIC |---|---|---|
# MAGIC | Private per user | Verified end-user identity | A support agent remembers one user's preferences |
# MAGIC | Shared group | Fixed team, project, or org key | A team glossary of company terms |
# MAGIC | Split by other values | Your own key, such as `{tenant}:{user}` | Isolating customers in a multi-tenant app |
# MAGIC
# MAGIC | Permission | Meaning |
# MAGIC |---|---|
# MAGIC | **READ** | Read store data |
# MAGIC | **WRITE** | Read and write store data (includes READ) |
# MAGIC | Creator | Implicit WRITE; can grant, list, and revoke; can't be revoked |
# MAGIC
# MAGIC Only the store creator or a workspace admin can manage permissions. Being an admin doesn't
# MAGIC grant data access. Grants go to users or service principals, not groups. Any workspace user
# MAGIC can list and get stores, including their IDs and descriptions.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4.1 Check your access, and grant the Lab Console app
# MAGIC
# MAGIC The Lab Console app runs as its own **service principal**, so it can open your stores only
# MAGIC after you grant it access. Granting is idempotent, so re-running the cell is safe.

# COMMAND ----------

print(f"Your access: sessions={session_store.get_permission().permission} "
      f"memory={memory_store.get_permission().permission}")

try:
    app_info = w.apps.get(APP_NAME)
    app_sp = getattr(app_info, "effective_service_principal_client_id", None) or app_info.service_principal_client_id
except Exception as e:
    app_sp = None
    print(f"Lab Console app '{APP_NAME}' not found ({type(e).__name__}); skipping the app grant.")

if app_sp:
    session_store.grant_permission(app_sp, permission="WRITE")
    memory_store.grant_permission(app_sp, permission="WRITE")
    print(f"✓ Granted the Lab Console app ({app_sp}) WRITE on both stores")
    for g in memory_store.list_permissions():
        print(f"  {MEMORY_STORE_ID}: {g.principal.principal_type} {g.principal.name} → {g.permission}")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Part 5: Reference: Self-Managed Memory on Lakebase
# MAGIC
# MAGIC Earlier versions of this lab built agent memory directly on Lakebase tables.
# MAGIC `00_Setup_Lakebase_Project` still creates them in your schema: `agent_sessions` and
# MAGIC `agent_messages` (short-term), and `agent_memory_store` (long-term key-value).
# MAGIC
# MAGIC ![Self-managed agent memory on Lakebase](../../docs/images/agent_memory_architecture.png)
# MAGIC
# MAGIC ```python
# MAGIC # Short-term: one row per message, replayed in order
# MAGIC cur.execute("INSERT INTO agent_messages (session_id, role, content) VALUES (%s, %s, %s)",
# MAGIC             (thread_id, "user", "How does branching work?"))
# MAGIC cur.execute("SELECT role, content FROM agent_messages WHERE session_id = %s ORDER BY created_at",
# MAGIC             (thread_id,))
# MAGIC
# MAGIC # Long-term: key-value upsert per user + topic
# MAGIC cur.execute("""INSERT INTO agent_memory_store (user_id, topic, memory) VALUES (%s, %s, %s)
# MAGIC                ON CONFLICT (user_id, topic) DO UPDATE SET memory = EXCLUDED.memory""",
# MAGIC             (user_email, "preferred_language", "Python"))
# MAGIC
# MAGIC # LangGraph checkpointing straight to Lakebase
# MAGIC from langgraph.checkpoint.postgres import PostgresSaver
# MAGIC graph = builder.compile(checkpointer=PostgresSaver.from_conn_string(conn_string))
# MAGIC ```
# MAGIC
# MAGIC | | Managed sessions + memory | Self-managed on Lakebase |
# MAGIC |---|---|---|
# MAGIC | **Schema & SQL** | None; SDK or REST API | You design tables and write queries |
# MAGIC | **Recall** | Built-in keyword (BM25) + semantic search | What you build (for example, pgvector or BM25) |
# MAGIC | **Distillation** | Memory pipelines | Your own extraction code |
# MAGIC | **Access control** | Per-store READ / WRITE grants | Postgres roles and grants |
# MAGIC | **Choose when** | You want storage, search, and distillation managed for you | You need a custom schema, joins with operational data, or full SQL control |

# COMMAND ----------

# MAGIC %md
# MAGIC ## Clean Up (Optional)
# MAGIC
# MAGIC A workspace holds up to 50 memory stores, so delete yours when you're done. Deleting a store
# MAGIC deletes its data; deleting the pipeline doesn't. The Lab Console's Agent Memory page stops
# MAGIC working for you until you re-run this notebook.

# COMMAND ----------

# UNCOMMENT TO CLEAN UP:
# w.api_client.do("DELETE", f"{AGENTS_API}/{PIPELINE_NAME}")
# client.memory_stores.get(MEMORY_STORE_ID).delete()
# client.session_stores.get(SESSION_STORE_ID).delete()
# print(f"✓ Deleted {PIPELINE_NAME}, {MEMORY_STORE_ID}, and {SESSION_STORE_ID}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's Next?
# MAGIC
# MAGIC Continue to another lab path:
# MAGIC
# MAGIC | Path | Folder | What You'll Learn |
# MAGIC |------|--------|-------------------|
# MAGIC | **Data Operations** | `labs/data-operations/` | CRUD, JSONB queries, array operators, audit triggers, transactions |
# MAGIC | **Lakebase Search** | `labs/lakebase-search/` | Vector + BM25 + hybrid search in Postgres |
# MAGIC | **Reverse ETL** | `labs/reverse-etl/` | Sync Delta Lake tables into Lakebase for low-latency serving |
# MAGIC | **Development Experience** | `labs/development-experience/` | Git-like branching, autoscaling compute, scale-to-zero |
# MAGIC | **Observability** | `labs/observability/` | pg_stat views, index analysis, connection monitoring |
# MAGIC | **Authentication** | `labs/authentication/` | OAuth tokens, two-layer permissions, role grants |
# MAGIC | **Backup & Recovery** | `labs/backup-recovery/` | Checkpoint branches, snapshots, point-in-time restore |
# MAGIC | **Online Feature Store** | `labs/online-feature-store/` | Real-time ML feature serving powered by Lakebase Autoscaling |
# MAGIC | **App Deployment** | `labs/app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |
