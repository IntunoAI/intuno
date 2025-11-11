# 🧠 Intuno Demo

This demo showcases the Intuno system with multiple simulated agents communicating through the registry and broker.

## 🚀 Quick Start

### 1. Start the Intuno Server
```bash
# Install dependencies
pip install -e .

# Start the server
uvicorn src.main:app --reload
```

The server will be available at:
- **API**: http://localhost:8000
- **Web Interface**: http://localhost:8000/static/index.html
- **API Docs**: http://localhost:8000/docs

### 2. Setup Demo Agents
```bash
# Register mock agents and create demo user
python scripts/setup_demo.py
```

### 3. Start Mock Agent Servers
```bash
# Start simulated agents (ports 8001-8004)
python -m src.simulators.mock_agents
```

## 🤖 Demo Agents

The demo includes 4 simulated agents:

### 1. **PDF Summarizer** (`agent:demo:pdf_summarizer:1.0.0`)
- **Capabilities**: `summarize_pdf`, `extract_text`
- **Endpoint**: http://localhost:8001
- **Purpose**: Summarizes PDF documents with key points

### 2. **Multi-Language Translator** (`agent:demo:translator:1.0.0`)
- **Capabilities**: `translate_text`, `detect_language`
- **Endpoint**: http://localhost:8002
- **Purpose**: Translates text between languages

### 3. **Smart Task Scheduler** (`agent:demo:scheduler:1.0.0`)
- **Capabilities**: `schedule_task`, `list_tasks`
- **Endpoint**: http://localhost:8003
- **Purpose**: Manages tasks and schedules

### 4. **Weather Information Agent** (`agent:demo:weather:1.0.0`)
- **Capabilities**: `get_weather`
- **Endpoint**: http://localhost:8004
- **Purpose**: Provides weather information

## 🎯 Demo Scenarios

### Scenario 1: Web Interface
1. Open http://localhost:8000/static/index.html
2. Browse the agent registry
3. Test individual agent invocations
4. View invocation logs
5. Run the demo workflow

### Scenario 2: API Testing
```bash
# Register a user
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test123"}'

# Login
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test123"}'

# Browse agents
curl "http://localhost:8000/registry/agents"

# Invoke an agent
curl -X POST "http://localhost:8000/broker/invoke" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "agent_id": "agent:demo:translator:1.0.0",
    "capability_id": "translate_text",
    "input": {"text": "Hello world", "target_lang": "es"}
  }'
```

### Scenario 3: Multi-Agent Workflow
The demo includes a complete workflow that:
1. Translates a document from Spanish to English
2. Summarizes the translated text
3. Schedules a follow-up task
4. Checks the weather for the meeting location

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Frontend  │    │  Intuno Server  │    │  Mock Agents    │
│                 │    │                 │    │                 │
│  - Registry UI  │◄──►│  - Registry API │◄──►│  - PDF Summarizer│
│  - Invoke UI    │    │  - Broker API   │    │  - Translator   │
│  - Logs UI      │    │  - Auth API     │    │  - Scheduler    │
│  - Demo UI      │    │  - Web Interface│    │  - Weather      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🔧 Features Demonstrated

### Registry Features
- ✅ Agent registration and discovery
- ✅ Semantic search capabilities
- ✅ Capability-based filtering
- ✅ Agent versioning and metadata

### Broker Features
- ✅ Agent invocation proxying
- ✅ Request/response logging
- ✅ Error handling and timeouts
- ✅ Performance monitoring

### Authentication Features
- ✅ User registration and login
- ✅ JWT token authentication
- ✅ API key management
- ✅ User-specific agent ownership

### Web Interface Features
- ✅ Agent registry browser
- ✅ Interactive agent invocation
- ✅ Real-time invocation logs
- ✅ Multi-agent workflow demo

## 📊 Monitoring

### Invocation Logs
- View all agent invocations
- Filter by user, agent, or status
- Monitor performance metrics
- Track error rates

### Agent Performance
- Response times
- Success rates
- Error patterns
- Usage statistics

## 🛠️ Development

### Adding New Mock Agents
1. Add agent definition to `src/simulators/mock_agents.py`
2. Implement mock response logic
3. Register with Intuno using setup script

### Customizing the Frontend
- Edit `src/static/index.html`
- Add new features to the web interface
- Customize the UI/UX

### Extending the API
- Add new endpoints to existing routers
- Create new feature modules
- Implement additional authentication methods

## 🐛 Troubleshooting

### Common Issues

**"Could not connect to Intuno server"**
- Make sure the server is running on port 8000
- Check if the port is already in use

**"Mock agents not responding"**
- Ensure mock agents are running on ports 8001-8004
- Check for port conflicts

**"Authentication failed"**
- Use the demo credentials: `demo@intuno.io` / `demo123`
- Or register a new user through the API

**"Agent invocation failed"**
- Verify the agent is registered in the registry
- Check that the mock agent server is running
- Review the invocation logs for errors

### Logs and Debugging
- Check server logs for detailed error messages
- Use the web interface logs tab to monitor invocations
- Review the API documentation at `/docs`

## 🎉 Success Criteria

The demo successfully demonstrates:
- ✅ Multiple agents can be registered and discovered
- ✅ Agents can be invoked through the broker
- ✅ Cross-agent workflows are possible
- ✅ All interactions are logged and monitored
- ✅ The system is accessible through both API and web interface

This creates a foundation for building real AI agent ecosystems where agents can discover, communicate, and collaborate autonomously!
