# Agentic Memory

Use Lakebase as persistent memory for AI agents — both short-term conversation history and long-term knowledge extraction across sessions.

## Labs

| Lab | What You'll Learn |
|-----|-------------------|
| `Agent_Memory` | Short-term memory (thread-based conversations), long-term memory (key-value knowledge store), querying both layers, framework integration patterns |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation — seeds the `agent_sessions`, `agent_messages`, and `agent_memory_store` tables)

## Key Concepts

- **Short-term memory** — Entire conversations stored per thread ID using checkpointing; maintains context for follow-up questions within a session
- **Long-term memory** — Key information extracted from multiple conversations and stored as key-value pairs; enables personalization across sessions
- **Lakebase checkpoint saver** — Frameworks like LangGraph use Lakebase as a checkpoint backend for durable agent state
- **No extra infrastructure** — Use the same Lakebase instance your app already connects to

## Documentation

- [AI agent memory](https://docs.databricks.com/aws/en/generative-ai/agent-framework/stateful-agents)
- [What is Lakebase Autoscaling?](https://docs.databricks.com/aws/en/oltp/projects/about)
- [Connect to your database](https://docs.databricks.com/aws/en/oltp/projects/connect)

## App Templates

| Framework | Template | Memory Types |
|-----------|----------|-------------|
| LangGraph | `agent-langgraph-advanced` | Short-term + Long-term |
| OpenAI Agents SDK | `agent-openai-advanced` | Short-term |

```bash
git clone https://github.com/databricks/app-templates.git
cd app-templates/agent-langgraph-advanced
```
