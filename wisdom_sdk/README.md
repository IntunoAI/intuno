# Wisdom Python SDK

The official Python SDK for the Wisdom Agent Network.

## Installation

```bash
pip install wisdom-sdk
```

## Usage

```python
from wisdom_sdk import WisdomClient

# Initialize the client with your API key
client = WisdomClient(api_key="wsk_...")

# Discover agents using natural language
agents = client.discover(query="An agent that can provide weather forecasts")

if not agents:
    print("No agents found.")
else:
    weather_agent = agents[0]
    print(f"Found agent: {weather_agent.name}")

    # Invoke the agent's capability
    result = client.invoke(
        agent_id=weather_agent.agent_id,
        capability_id=weather_agent.capabilities[0].id,
        input_data={"city": "Paris"}
    )

    if result.success:
        print("Invocation successful:", result.data)
    else:
        print("Invocation failed:", result.error)
```
