# Intuno Demo

This demo showcases how easy it is to register, discover, and invoke agents in the Intuno network.

## What This Demo Shows

1. **Account Creation**: Create a new user account
2. **API Key Generation**: Generate an API key for authentication
3. **Agent Registration**: Register multiple agents with their capabilities
4. **Agent Discovery**: Use semantic search to find agents
5. **Agent Invocation**: Invoke agent capabilities through the broker

## Prerequisites

- Python 3.10+
- The main Intuno server running on `http://localhost:8000`
- Database configured and migrations run

## Setup

1. **Install dependencies**:
   ```bash
   cd demo
   pip install -r requirements.txt
   ```

2. **Start the main Intuno server** (in the project root):
   ```bash
   # Make sure your database is running and migrations are applied
   uvicorn src.main:app --reload
   ```

3. **Start the demo agent servers**:

   **Option A: Using the shell script (recommended)**
   ```bash
   cd demo
   ./start_agents.sh
   ```

   **Option B: Start each agent in separate terminals**
   ```bash
   # Terminal 1 - Calculator Agent
   cd demo
   python agents/calculator_agent.py

   # Terminal 2 - Text Processor Agent
   python agents/text_processor_agent.py

   # Terminal 3 - Weather Agent
   python agents/weather_agent.py
   ```

   Each agent will run on a different port:
   - Calculator: `http://localhost:8001`
   - Text Processor: `http://localhost:8002`
   - Weather: `http://localhost:8003`

## Running the Demo

Once all services are running, execute the demo script:

```bash
cd demo
python demo.py
```

The script will:
1. Create a new user account
2. Generate an API key
3. Register all three agents
4. Demonstrate discovery with different queries
5. Invoke various capabilities from the registered agents

## Demo Agents

### 1. Calculator Agent (`http://localhost:8001`)
- **add**: Adds two numbers
- **subtract**: Subtracts two numbers
- **multiply**: Multiplies two numbers

### 2. Text Processor Agent (`http://localhost:8002`)
- **uppercase**: Converts text to uppercase
- **lowercase**: Converts text to lowercase
- **reverse**: Reverses a string

### 3. Weather Agent (`http://localhost:8003`)
- **get_weather**: Returns hardcoded weather data for a city

## Expected Output

The demo script will print each step with clear output showing:
- Account creation success
- API key generation
- Agent registration confirmations
- Discovery results
- Invocation results with data

## Alternative: Using the SDK

The demo script uses direct HTTP calls for simplicity. You can also use the Intuno SDK:

```python
from intuno_sdk import IntunoClient

client = IntunoClient(api_key="your-api-key")

# Discover agents
agents = client.discover(query="I need to do math calculations")

# Invoke a capability
result = agents[0].invoke("add", {"a": 5, "b": 3})
```

## Cleanup

To clean up the demo data, you can manually delete the registered agents through the API or reset your database.

