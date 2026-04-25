# Frontend Integration Guide

## Quick Connect

Your frontend (Jarvis on Vercel) needs to call these endpoints:

### Main Question Endpoint
```
POST /api/ask
```

**Request:**
```json
{
  "query": "Tell me about Shell SPDC",
  "session_id": "optional-user-session-id"
}
```

**Response:**
```json
{
  "answer": "Shell operates in Nigeria through Shell Petroleum Development Company (SPDC)...",
  "entity_id": "shell-spdc",
  "entity_name": "Shell Petroleum Development Company",
  "session_id": "generated-or-provided-id",
  "is_success": true
}
```

### Implementation Examples

#### JavaScript/React (Recommended for Vercel)
```javascript
// hooks/useCerebroAPI.ts
import { useCallback, useState } from 'react';

export function useCerebroAPI() {
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string>();

  const askQuestion = useCallback(async (query: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(
        'http://localhost:8000/api/ask', // Change to backend URL in production
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, session_id: sessionId })
        }
      );
      
      const data = await response.json();
      setSessionId(data.session_id); // Store for follow-ups
      
      return {
        answer: data.answer,
        entity: data.entity_name,
        isSuccess: data.is_success
      };
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  return { askQuestion, isLoading, sessionId };
}

// In your Jarvis component
export function JarvisChat() {
  const { askQuestion, isLoading, sessionId } = useCerebroAPI();
  const [messages, setMessages] = useState<Message[]>([]);

  async function handleUserMessage(userQuery: string) {
    setMessages(prev => [...prev, { role: 'user', content: userQuery }]);
    
    const result = await askQuestion(userQuery);
    
    setMessages(prev => [...prev, { role: 'assistant', content: result.answer }]);
  }

  return (
    <ChatInterface
      messages={messages}
      onSubmit={handleUserMessage}
      isLoading={isLoading}
    />
  );
}
```

#### Python (if you have a backend proxy)
```python
import httpx

class CerebroClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session_id = None
    
    async def ask(self, query: str) -> dict:
        """Ask a question to the Cerebro pipeline."""
        response = await httpx.AsyncClient().post(
            f"{self.base_url}/api/ask",
            json={"query": query, "session_id": self.session_id}
        )
        data = response.json()
        
        # Store session for follow-ups
        self.session_id = data["session_id"]
        
        return {
            "answer": data["answer"],
            "entity": data["entity_name"],
            "success": data["is_success"]
        }

# Usage
client = CerebroClient()
result = await client.ask("Tell me about NNPC")
print(result["answer"])
```

#### cURL (for testing)
```bash
# Simple question
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Tell me about Shell"}'

# With session (for follow-ups)
SESSION_ID="abc123-uuid"
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"Their production?\",\"session_id\":\"$SESSION_ID\"}"
```

## Session Management for Follow-Ups

### How Sessions Work

1. **First question**: User asks about an entity
   ```
   User: "Tell me about Shell"
   Backend stores: session_id="xyz", current_entity="shell-spdc"
   ```

2. **Follow-up question**: Backend remembers context
   ```
   User: "What's their production?"
   Backend: Uses stored current_entity="shell-spdc"
   ```

### Frontend Implementation

```javascript
// Store session ID in localStorage or context
const CerebroContext = createContext<{
  sessionId: string;
  askQuestion: (query: string) => Promise<string>;
}>({
  sessionId: '',
  askQuestion: async () => ''
});

export function CerebroProvider({ children }) {
  const [sessionId, setSessionId] = useState(
    localStorage.getItem('cerebroSessionId') || generateUUID()
  );

  useEffect(() => {
    localStorage.setItem('cerebroSessionId', sessionId);
  }, [sessionId]);

  const askQuestion = async (query: string) => {
    const response = await fetch('/api/ask', {
      method: 'POST',
      body: JSON.stringify({ query, session_id: sessionId })
    });
    return response.json();
  };

  return (
    <CerebroContext.Provider value={{ sessionId, askQuestion }}>
      {children}
    </CerebroContext.Provider>
  );
}
```

## Helpful Utility Endpoints

### Get All Entities
```bash
GET /api/entities?entity_type=UpstreamProducer
```

Returns:
```json
{
  "entities": [
    {"id": "shell-spdc", "name": "Shell SPDC", "short_name": "Shell"},
    {"id": "nnpc-limited", "name": "NNPC Limited", "short_name": "NNPC"},
    ...
  ],
  "count": 54
}
```

**Use for**: Entity autocomplete, dropdown lists

### Search Entities
```bash
GET /api/search?query=Shell
```

Returns matches like `/api/entities`

**Use for**: Search suggestions as user types

### Get Entity Details
```bash
GET /api/entity/shell-spdc
```

Returns:
```json
{
  "entity": {"id": "shell-spdc", "name": "...", "short_name": "..."},
  "available_properties": {
    "name": "STRING",
    "ioc_equity_percentage": "FLOAT",
    "production_bopd": "STRING",
    ...
  },
  "property_count": 45
}
```

**Use for**: Entity profile pages, property inspection

### Get Session History
```bash
GET /api/session/abc123-uuid
```

Returns:
```json
{
  "session_id": "abc123-uuid",
  "created_at": "2026-04-16T10:30:00",
  "current_entity": {"id": "shell-spdc", "name": "Shell SPDC"},
  "visited_entities": ["shell-spdc", "nnpc-limited"],
  "conversation_history": [
    {"role": "user", "content": "Tell me about Shell"},
    {"role": "assistant", "content": "..."}
  ]
}
```

**Use for**: Conversation replay, debugging

## Deployment Configuration

### Local Development
```env
CEREBRO_API_URL=http://localhost:8000
```

### Production (Deployed Backend)
```env
CEREBRO_API_URL=https://cerebro-backend.railway.app  # Or your cloud URL
```

### Example Next.js Config
```typescript
// next.config.js
const CEREBRO_API = process.env.CEREBRO_API_URL || 'http://localhost:8000';

module.exports = {
  env: {
    NEXT_PUBLIC_CEREBRO_API: CEREBRO_API
  }
};

// lib/cerebro.ts
const API_URL = process.env.NEXT_PUBLIC_CEREBRO_API!;

export async function askCerebroQuestion(query: string, sessionId?: string) {
  const response = await fetch(`${API_URL}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, session_id: sessionId })
  });
  return response.json();
}
```

## CORS Handling

The backend allows all origins by default (for MVP). For production, update `main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend.vercel.app"],  # Specify frontend URL
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
```

## Error Handling

Common error responses:

### 400 Bad Request
```json
{
  "detail": "Query cannot be empty"
}
```

**Fix**: Ensure query is provided and non-empty

### 503 Service Unavailable
```json
{
  "detail": "LLM Pipeline not available. Check GITHUB_TOKEN."
}
```

**Fix**: Set GITHUB_TOKEN in environment

### 500 Internal Server Error
```json
{
  "detail": "Pipeline error: ..."
}
```

**Fix**: Check server logs for details

## Testing the Connection

### 1. Check Health
```bash
curl http://localhost:8000/health
# Should return: {"status":"ok","database":"connected","llm":"ready"}
```

### 2. Test Entity Search
```bash
curl "http://localhost:8000/api/search?query=NNPC"
# Should return array of NNPC results
```

### 3. Test Full Pipeline
```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Tell me about NNPC"}'
# Should return: answer, entity_id, session_id, is_success
```

## Troubleshooting

### "Cannot connect to backend"
- Ensure backend is running: `python3 main.py`
- Check port 8000 is accessible
- In Vercel, need to use absolute URL (not localhost)
- Add backend domain to environment variables

### "CORS error in browser"
- Backend allows all origins by default
- Check browser console for specific error
- May need to deploy backend to public URL

### "Empty or incorrect answers"
- Verify entities are seeded to Neo4j database
- Test `/api/entities` to confirm data exists
- Check GITHUB_TOKEN is valid

---

**Questions?** Check the [Backend README](./cerebro_backend/README.md) or [LLM Guide](./LLM_QUERY_PIPELINE_GUIDE.md)
