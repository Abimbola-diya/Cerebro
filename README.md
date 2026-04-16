<<<<<<< HEAD
# Cerebro AI Pipeline - MVP Backend

## Overview

FastAPI backend implementing the 7-step LLM query pipeline for Nigerian upstream oil & gas data.


## Architecture

```
User Query → FastAPI → 7-Step Pipeline → Answer
                ↓
        Neo4j Database (Query A, B, C)
                ↓
        GitHub Models LLM (Synthesis)
```

### 7-Step Pipeline (from LLM_QUERY_PIPELINE_GUIDE.md)

1. Load node catalog
2. Identify entity type (UpstreamProducer, FPSOOperator, etc.)
3. Query all entities (Query A)
4. Disambiguate/match entity (consider session context)
5. Discover properties (Query B)
6. Filter by relevance
7. Retrieve data & synthesize answer (Query C)

## Setup

### 1. Install Dependencies

```bash
cd cerebro_backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

The `.env` file is already configured with:

**⚠️ Security Note**: Keep `.env` secret. Never commit to git.

### 3. Run Server

```bash
python main.py
```

Server starts at: `http://localhost:8000`

API Docs (interactive): `http://localhost:8000/docs`

## Endpoints

### POST `/api/ask`
Main endpoint - Answer questions about upstream producers

**Request:**
```json
{
  "query": "Tell me about Shell",
  "session_id": "optional-uuid"
}
```

**Response:**
```json
{
  "answer": "Shell operates in Nigeria through SPDC (Shell Petroleum Development Company)...",
  "entity_id": "shell-spdc",
  "entity_name": "Shell SPDC",
  "session_id": "uuid",
  "is_success": true
}
```

### GET `/api/entities`
List all entities (with optional type filter)

```bash
curl http://localhost:8000/api/entities?entity_type=UpstreamProducer
```

### GET `/api/search`
Search entities by keyword

```bash
curl "http://localhost:8000/api/search?query=Shell"
```

### GET `/api/entity/{entity_id}`
Get entity details and available properties

```bash
curl http://localhost:8000/api/entity/shell-spdc
```

### GET `/api/session/{session_id}`
Get session history and context

### DELETE `/api/session/{session_id}`
Clear session

### GET `/health`
Health check - verify all services

### GET `/api/test`
Test the pipeline with a sample query

## Testing the Pipeline

### Test 1: Simple Entity Query
```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Tell me about Shell"}'
```

### Test 2: Follow-up Question (Session Memory)
```bash
# Get session_id from Test 1
SESSION_ID="your-session-id"

# Ask follow-up
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"What is their production?\",\"session_id\":\"$SESSION_ID\"}"
```

### Test 3: List All Entities
```bash
curl http://localhost:8000/api/entities
```

### Test 4: Health Check
```bash
curl http://localhost:8000/health
```

### Test 5: Run Integrated Test
```bash
curl http://localhost:8000/api/test
```

## File Structure

```
cerebro_backend/
├── main.py              # FastAPI app + endpoints
├── database.py          # Neo4j driver + Query A/B/C
├── llm.py               # LLM pipeline (7 steps)
├── session.py           # Session memory management
├── requirements.txt     # Python dependencies
├── .env                 # Configuration (secrets)
├── .env.example         # Template (for git)
└── README.md            # This file
```

## How It Works

### Query Flow Example: "Tell me about Shell"

1. **Step 1**: Load node catalog (UpstreamProducer, FPSOOperator, etc.)
2. **Step 2**: Identify type → Keywords "about Shell" → Entity = UpstreamProducer
3. **Step 3**: Query all UpstreamProducers → Get [{id, name}, ...]
4. **Step 4**: Match "Shell" to entity → Find "shell-spdc" or similar
5. **Step 5**: Discover properties on shell-spdc → {name, equity%, production, reserves, ...}
6. **Step 6**: Filter by relevance → Keep: name, equity%, production, reserves, headquarters
7. **Step 7**: Retrieve data → Get values for filtered properties → LLM synthesizes answer

### Session Example: Follow-up Question

```
User: "Tell me about Shell"
→ Pipeline finds entity: shell-spdc
→ Session memory stores: {current_entity_id: "shell-spdc", current_entity_name: "Shell SPDC"}

User: "What is their production?"
→ Step 4 checks session context
→ Uses stored entity: shell-spdc (no need to disambiguate)
→ Filter for production-related properties
→ Return production data
```

## Key Design Decisions

### 1. Database-First Property Discovery

### 2. Session Memory

### 3. LLM Synthesis Only

## Troubleshooting

### "GITHUB_TOKEN not set"

### "Failed to connect to Neo4j"

### "Connection timeout"

### Empty results from `/api/ask`

## Next Steps

1. **Local Testing** ✅ (currently here)
2. **Seed entities to Neo4j** (run `neo4j_seeding.py` if not already done)
3. **Frontend Integration** (connect Vercel Jarvis to `POST /api/ask`)
4. **Deploy to Cloud** (Vercel, Railway, or similar)

## Performance Notes


**Total request time**: ~3-7 seconds per query

## Future Enhancements

=======
# Cerebro
Building the future.
# Cerebro

> *The software the 2008 market crash would have needed before it happened.*

---

## What Is This Repository?

This repository contains the foundational documentation, architecture, and design philosophy for **Cerebro** — an intelligent, interconnected, self-sustaining intelligence layer built on top of the petrochemical industry, starting with Nigeria.

Cerebro is not a dashboard. It is not a reporting tool. It is not a BI platform with prettier charts.

Cerebro is the thing that sits above all of that — the layer that understands the data, connects it, reasons through it, and tells you what is going to happen before it does.

---

## Documentation Index

| Document | Description |
|---|---|
| `CEREBRO.docx` | Full product specification — what Cerebro is, what it does, how it thinks, and why it matters |
| `README.md` | This file — orientation and navigation guide for the repository |

---

## The Core Idea

Every major industry collapse, every supply chain disruption, every commodity crisis — they all had indicators. Subtle ones. Ones that were there if you knew how to look and where to connect the dots.

Cerebro is built on the belief that **the future is the sum of all moments different from the present**, and that those differences are always telegraphed in the data, in the relationships between entities, in the flows of money and commodity and supply. You just need something intelligent enough to read them.

We start with the Nigerian petrochemical industry because it is one of the most consequential, most opaque, and most relationship-dense industries on the planet. Every refinery, every supplier, every trader, every government body, every logistics route — they all affect each other. Pull one node and the ecosystem shifts. Cerebro maps that shift before it happens.

---

## How to Navigate the Documentation

If you are reading this for the first time, start with **`CEREBRO.docx`**. It covers:

- What Cerebro is and the problem it is solving
- The Node Engine — how every entity in the petrochemical industry becomes a node, and how those nodes relate to each other
- The three views — Ecosystem View, End-to-End View, and Sankey View
- The three tools — Research, Visualization, and Inference
- The intelligence layer — how Cerebro answers *what if*, *why*, *when*, and *how*
- The confidence-scored simulation engine
- The natural language interface
- Why this company is worth building

---

## The Vision in One Paragraph

Cerebro puts the entire petrochemical industry in the cloud. It maps every entity — every player, every route, every relationship, every dependency — and creates a living digital twin that you can interrogate in real time. You can see the whole ecosystem or zoom into a single node. You can ask what happens if a refinery goes offline. You can trace exactly how a commodity moves from extraction to export. You can watch the flows of money, supply, and trade in real time. And when Cerebro detects something — an anomaly, a pattern, a cascading risk — it does not just flag it. It explains it, shows you who it affects, what they can do about it, and gives you a confidence score on how certain it is.

---

## Technology Philosophy

Cerebro is data-driven first. Intelligence second. Visualization third.

The research tool gathers. The inference engine makes sense of what it gathered. The visualization tool makes that sense visible to a human being in a way that requires no technical expertise to interpret.

Users communicate with Cerebro in natural language. Cerebro does the rest autonomously.

---

## Status

This repository currently holds the product vision and documentation layer. Architecture, data models, node schema definitions, and the inference engine design are the next stage.

---

## A Final Word

> *What valuable company is nobody building?*

The honest answer is: a company that can predict systemic collapse before it collapses. Every great company is a conspiracy to change the world. Cerebro is that conspiracy — starting with the Nigerian petrochemical industry, with the ambition of eventually being the intelligence layer that any complex, interconnected industry in the world cannot afford to operate without.
>>>>>>> c823570df9c5987e4c332b7d261fbf8d44beb66b
