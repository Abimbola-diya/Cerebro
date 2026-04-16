# 🚀 Cerebro AI Backend - Production Grade

## 📋 Overview

Production-grade Nigerian upstream petroleum AI query system with:
- ✅ **7-Step Intelligent Pipeline**: Entity identification → Disambiguation → Data retrieval → Synthesis
- ✅ **Fuzzy Entity Matching**: Handles typos, partial names, similar entities
- ✅ **Comprehensive Error Handling**: Graceful degradation, fallbacks, timeouts
- ✅ **Input Validation**: SQL injection prevention, special character handling, length limits
- ✅ **Web Search Integration**: Tavily discovery + Firecrawl deep scraping
- ✅ **Session Management**: Follow-up queries, conversation history
- ✅ **Production Logging**: Request tracking, performance metrics, error logging

## 🛠️ Architecture

```
User Query
    ↓
Input Validation & Sanitization
    ↓
Entity Identification (UpstreamProducer, etc.)
    ↓
Load All Entities (Neo4j)
    ↓
Entity Disambiguation (Fuzzy Matching)
    ↓
Property Discovery & Filtering
    ↓
Data Retrieval (Database + Web)
    ↓
Answer Synthesis (Natural Language)
    ↓
JSON Response
```

## 🚀 Quick Start

### Prerequisites
```bash
# Python 3.8+
# Environment variables set (.env file)
# Neo4j Aura credentials
# GitHub Models API token
# Tavily API key (for web search)
# Firecrawl API key (for web scraping)
```

### Installation
```bash
cd cerebro_backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration
Create `.env` file:
```
GITHUB_TOKEN=<your-github-token>
NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<password>
TAVILY_API_KEY=<api-key>
FIRECRAWL_API_KEY=<api-key>
```

### Run Server
```bash
# Option 1: Direct run
python main.py

# Option 2: With logging
python main.py 2>&1 | tee server.log

# Option 3: Production (with gunicorn)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 main:app --timeout 120
```

Server starts at: `http://localhost:8000`

## 📡 API Endpoints

### 1. Health Check
```
GET /health
```
**Response:**
```json
{
  "status": "ok",
  "database": "connected",
  "llm": "ready"
}
```

### 2. Ask Question
```
POST /api/ask
Content-Type: application/json

{
  "query": "Tell me about NNPC",
  "session_id": "optional-uuid"
}
```

**Response:**
```json
{
  "answer": "NNPC Exploration and Production Limited...",
  "entity_id": "nepl-nnpc-ep",
  "entity_name": "NNPC Exploration and Production Limited",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "is_success": true
}
```

### 3. List Entities
```
GET /api/entities?entity_type=UpstreamProducer
```

### 4. Search Entities
```
GET /api/search?query=shell&entity_type=UpstreamProducer
```

### 5. Get Entity Details
```
GET /api/entity/{entity_id}
```

### 6. Get Session Info
```
GET /api/session/{session_id}
```

## 🧪 Testing

### Run Production Test Suite
```bash
# Run all 28 tests
python test_production.py

# Tests cover:
# ✅ Input validation (empty, short, special chars)
# ✅ Single entity queries
# ✅ Block queries
# ✅ Production data queries
# ✅ Aggregation queries
# ✅ Typo tolerance
# ✅ Case insensitivity
# ✅ Error handling
# ✅ Follow-up queries
# ✅ API endpoints
```

### Use Swagger UI
Open in browser: `http://localhost:8000/docs`

**Try these queries:**
1. "Tell me about NNPC"
2. "What blocks does Shell have?"
3. "How much oil does Chevron produce?"
4. "Which company handles OML 188?"
5. "Rank companies by production"

### Manual Testing with cURL
```bash
# Health check
curl http://localhost:8000/health

# Ask question
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Tell me about NNPC"}'

# List entities
curl http://localhost:8000/api/entities

# Search entities
curl "http://localhost:8000/api/search?query=shell"
```

## 📊 Production Features

### Input Validation
- ✅ Query length 3-5000 characters
- ✅ Special character filtering
- ✅ Whitespace normalization
- ✅ SQL/Cypher injection prevention
- ✅ Type validation (string)

### Error Handling
- ✅ Graceful fallbacks for missing data
- ✅ Database connection retry logic
- ✅ Timeout handling (120s max per request)
- ✅ LLM API failure handling
- ✅ Web search timeout (30s)
- ✅ Detailed error messages
- ✅ Request ID tracking

### Entity Matching
- ✅ Exact name matching
- ✅ Fuzzy/Levenshtein-like matching
- ✅ Typo tolerance
- ✅ Partial name matching
- ✅ Short name aliases
- ✅ Case-insensitive search
- ✅ Confidence scoring

### Data Retrieval
- ✅ 12-40 properties per entity
- ✅ Null/empty field detection
- ✅ Data type validation
- ✅ Format conversion (string→numeric)
- ✅ Range validation

### Answer Synthesis
- ✅ Natural language generation
- ✅ Block information display (OML/OPL)
- ✅ Production data formatting
- ✅ Reserves information
- ✅ Equity structure
- ✅ Web source attribution
- ✅ Data source tracking

### Logging & Monitoring
- ✅ Request ID tracking
- ✅ Performance metrics per step
- ✅ Error tracking with context
- ✅ Debug mode (controlled by logging level)
- ✅ Query time tracking

## 🔍 Example Queries

### Single Entity
- "Tell me about NNPC"
- "What is Shell Nigeria?"
- "Mobil Producing information"
- "Tell me everything about Chevron"

### Block Queries
- "What blocks does NNPC have?"
- "How many OML blocks does Shell hold?"
- "Which blocks are operated by Total?"
- "Show me OML 65 details"

### Production Queries
- "What is the current production of NNPC?"
- "How much oil does Shell produce?"
- "Chevron's production rate?"
- "Where is Addax operating?"

### Aggregation Queries
- "Which company has the largest production?"
- "Rank companies by production capacity"
- "What is the average production?"
- "Smallest producer in the database"

### Advanced Queries
- "How many blocks does each company own?"
- "Compare NNPC vs Shell in terms of blocks"
- "Companies with operations in [field]"
- "List all entities in offshore operations"

## 🚨 Error Handling Examples

### Query too short
```
Query: "ab"
Response: 422 Unprocessable Entity
Detail: "Query must be at least 3 characters"
```

### Non-existent entity
```
Query: "Tell me about XYZ Corp"
Response: 200 OK
Answer: "Sorry, I couldn't find relevant information about that..."
```

### Typo tolerance
```
Query: "Tell me about Shel Nigeria"
Response: 200 OK (matches "Shell Nigeria" with fuzzy matching)
```

### API timeout
```
Response: 200 OK
Answer: "The system took too long to process your query. Please try a simpler question."
```

## 📈 Performance Metrics

Typical response times:
- Health check: <100ms
- Simple entity query: 5-15s
- Block query: 10-20s
- Aggregation query: 20-40s
- Web search included: +10-30s

## 🔧 Troubleshooting

### Server won't start
```bash
# Check logs for errors
python main.py 2>&1 | head -50

# Verify environment variables
echo $GITHUB_TOKEN
echo $NEO4J_URI

# Test database connection
python -c "from database import db; db.connect()"
```

### Empty answers
- Check if entity is in database: `GET /api/search?query=entityname`
- View entity details: `GET /api/entity/{entity_id}`
- Check logs for "Step 7a" to verify data retrieval

### Slow responses
- Check web search: May add 10-30s
- Review logs for timing at each step
- Try simpler queries first

## 📚 Database Schema

### Nodes
- **UpstreamProducer**: Oil & gas companies
  - Properties: name, short_name, id, headquarters_country, production_bopd, reserves_mmbbl, oml_blocks_held, opl_blocks_held, etc.
  - 54+ entities

### Query Examples
```cypher
# Find all producers
MATCH (p:UpstreamProducer) RETURN p LIMIT 5

# Find producer by name
MATCH (p:UpstreamProducer {name: "Shell Nigeria Exploration and Production Company Limited"}) RETURN p

# Find producers with specific blocks
MATCH (p:UpstreamProducer) WHERE "OML 65" IN p.oml_blocks_held RETURN p
```

## 📝 Logs

Logs are printed to stdout with format:
```
[LEVEL] timestamp - module: message
[DEBUG] - Pipeline steps, data retrieval
[INFO] - Requests, health checks
[WARNING] - Graceful failures, timeouts
[ERROR] - Exceptions, connection failures
```

Example:
```
[INFO] 2026-04-16 12:34:56,789 - main: [a1b2c3d4] Processing query: Tell me about NNPC...
[DEBUG] 2026-04-16 12:34:57,100 - llm: Single-entity query detected
[DEBUG] 2026-04-16 12:34:58,500 - llm: Step 7a: OML blocks='[OML 65, OML 13, ...]'
[INFO] 2026-04-16 12:34:59,123 - main: [a1b2c3d4] ✅ Completed in 3.33s
```

## 🎯 Next Steps

1. **Run Server**: `python main.py`
2. **Test Health**: `curl http://localhost:8000/health`
3. **Try Swagger**: http://localhost:8000/docs
4. **Run Tests**: `python test_production.py`
5. **Monitor Logs**: `tail -f server.log`

## 📞 Support

For issues:
1. Check logs for [ERROR] or [WARNING] messages
2. Run health check: `GET /health`
3. Try `/api/search?query=...` to verify entities exist
4. Review test suite results: `python test_production.py`

---

**Status**: ✅ Production Ready  
**Last Updated**: April 16, 2026  
**Python**: 3.8+
