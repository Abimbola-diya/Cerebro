# Planner Streaming API

## Endpoint
- Method: POST
- Path: /api/planner/stream
- Content-Type: application/json
- Response: text/event-stream (SSE)

## Request Body
```json
{
  "query": "What are the latest regulatory risks for Seplat?",
  "entity_id": "seplat-energy",
  "entity_name": "Seplat Energy",
  "entity_context": {
    "country": "Nigeria"
  },
  "max_attempts": 3
}
```

All fields except query are optional.
If max_attempts is omitted, the API uses a default of 3 attempts.

## Stream Events
1. start
```json
{"status":"started"}
```
2. thinking_delta
```json
{"delta":"...incremental planner reasoning text..."}
```
3. plan
```json
{"plan": {"query":"...","thinking":"...","research_plan": {...},"_meta": {...}}}
```
4. done
```json
{"status":"ok"}
```

On failure, the stream emits:
1. error
```json
{"message":"...error details..."}
```
2. done
```json
{"status":"error"}
```

## Timeout Controls
- PLANNER_STREAM_TIMEOUT_SECONDS (default: 45)
- PLANNER_TIMEOUT_SECONDS (default: 120)
- PLANNER_STREAM_EXCLUDE_MODELS (default: openai/gpt-5)

## JavaScript Client Example
```javascript
const response = await fetch('http://localhost:8000/api/planner/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: userQuery })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { value, done } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  const events = buffer.split('\n\n');
  buffer = events.pop() || '';

  for (const rawEvent of events) {
    const lines = rawEvent.split('\n');
    const eventLine = lines.find((line) => line.startsWith('event: '));
    const dataLine = lines.find((line) => line.startsWith('data: '));
    if (!eventLine || !dataLine) continue;

    const eventType = eventLine.replace('event: ', '').trim();
    const payload = JSON.parse(dataLine.replace('data: ', '').trim());

    if (eventType === 'thinking_delta') {
      renderThinkingDelta(payload.delta);
    }

    if (eventType === 'plan') {
      renderFinalPlan(payload.plan);
    }
  }
}
```
