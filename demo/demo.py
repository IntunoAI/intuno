"""
Intuno Demo Script

This script demonstrates the complete workflow:
1. Create an account
2. Generate an API key
3. Register agents
4. Discover agents
5. Invoke agent capabilities

Run this after starting:
- The main Intuno server (localhost:8000)
- The demo agent servers (ports 8001, 8002, 8003)
"""

import json
import time
from typing import Any, Callable, Dict, TypeVar

import httpx

T = TypeVar("T")

# Configuration
BASE_URL = "http://localhost:8000"
CALCULATOR_AGENT_URL = "http://localhost:8001"
TEXT_PROCESSOR_AGENT_URL = "http://localhost:8002"
WEATHER_AGENT_URL = "http://localhost:8003"


def print_step(step_num: int, title: str):
    """Print a formatted step header."""
    print(f"\n{'=' * 60}")
    print(f"STEP {step_num}: {title}")
    print(f"{'=' * 60}\n")


def print_success(message: str):
    """Print a success message."""
    print(f"✅ {message}")


def print_info(message: str):
    """Print an info message."""
    print(f"ℹ️  {message}")


def print_result(data: Any):
    """Print formatted result data."""
    print(json.dumps(data, indent=2, default=str))


def retry_request(
    func: Callable[[], T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (
        httpx.ReadError,
        httpx.ConnectError,
        httpx.TimeoutException,
        ConnectionError,
    ),
) -> T:
    """Retry a function call with exponential backoff for network errors.

    Args:
        func: The function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        backoff_factor: Multiplier for delay between retries
        retryable_exceptions: Tuple of exception types to retry on

    Returns:
        The result of the function call

    Raises:
        The last exception if all retries fail
    """
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except retryable_exceptions as e:
            last_exception = e
            if attempt < max_retries:
                print_info(
                    f"Connection error (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay *= backoff_factor
            else:
                print(f"❌ Failed after {max_retries + 1} attempts")
                raise

    # Should never reach here, but just in case
    if last_exception:
        raise last_exception
    raise Exception("Unexpected error in retry_request")


# Step 1: Create Account
def step1_create_account(client: httpx.Client) -> Dict[str, Any]:
    """Create a new user account."""
    print_step(1, "Creating Account")

    # Generate a unique email based on timestamp
    timestamp = int(time.time())
    email = f"demo_user_{timestamp}@example.com"
    password = "demo_password_123"

    print_info(f"Registering user: {email}")

    response = client.post(
        f"{BASE_URL}/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "Demo",
            "last_name": "User",
        },
    )
    response.raise_for_status()
    user_data = response.json()

    print_success("Account created successfully!")
    print_result(user_data)

    return {"email": email, "password": password, "user_id": user_data["id"]}


# Step 2: Login and Create API Key
def step2_create_api_key(client: httpx.Client, email: str, password: str) -> str:
    """Login and create an API key."""
    print_step(2, "Creating API Key")

    # Login to get JWT token
    print_info("Logging in...")
    login_response = client.post(
        f"{BASE_URL}/auth/login", json={"email": email, "password": password}
    )
    login_response.raise_for_status()
    token_data = login_response.json()
    access_token = token_data["access_token"]

    print_success("Login successful!")

    # Create API key using JWT token
    print_info("Creating API key...")
    api_key_response = client.post(
        f"{BASE_URL}/auth/api-keys",
        json={"name": "Demo API Key"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    api_key_response.raise_for_status()
    api_key_data = api_key_response.json()
    api_key = api_key_data["key"]

    print_success("API key created!")
    print_info(f"API Key: {api_key[:20]}...")

    return api_key


def register_or_get_agent(
    client: httpx.Client,
    headers: Dict[str, str],
    manifest: Dict[str, Any],
    agent_name: str,
) -> str:
    """Register an agent or get existing agent if it already exists."""
    agent_id = manifest["agent_id"]

    # Try to register the agent with retry logic
    def _register():
        return client.post(
            f"{BASE_URL}/registry/agents", json={"manifest": manifest}, headers=headers
        )

    response = retry_request(_register)

    if response.status_code == 201:
        # Successfully registered
        data = response.json()
        print_success(f"{agent_name} registered: {data['agent_id']}")
        return data["agent_id"]
    elif response.status_code == 400:
        # Check if it's an "already exists" error
        try:
            error_detail = response.json().get("detail", "")
        except Exception:
            error_detail = response.text

        if "already exists" in error_detail.lower():
            # Agent already exists, try to get it to verify
            print_info(f"{agent_name} already exists, retrieving existing agent...")

            def _get_agent():
                return client.get(
                    f"{BASE_URL}/registry/agents/{agent_id}", headers=headers
                )

            try:
                get_response = retry_request(_get_agent, max_retries=2)
                if get_response.status_code == 200:
                    data = get_response.json()
                    print_success(f"{agent_name} found: {data['agent_id']}")
                    return data["agent_id"]
                elif get_response.status_code == 404:
                    # Agent not found (might have been deleted)
                    print_info(
                        f"{agent_name} not found in database, will need to re-register"
                    )
                else:
                    # Other error
                    print_info(
                        f"Could not retrieve {agent_name} details (status {get_response.status_code})"
                    )
            except Exception as e:
                # If we can't get it, but we know it exists, just use the agent_id from manifest
                print_info(f"Could not retrieve {agent_name} details: {str(e)[:50]}")
                pass

            # If we can't get it, but we know it exists, just use the agent_id from manifest
            print_info(
                f"{agent_name} exists but couldn't retrieve details, using agent_id: {agent_id}"
            )
            return agent_id
        else:
            # Some other 400 error, raise it
            response.raise_for_status()
    else:
        # Some other error, raise it
        response.raise_for_status()

    # Should never reach here, but just in case
    raise Exception(f"Failed to register or get {agent_name}")


# Step 3: Register Agents
def step3_register_agents(client: httpx.Client, api_key: str) -> Dict[str, str]:
    """Register all demo agents."""
    print_step(3, "Registering Agents")

    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    registered_agents = {}

    # Register Calculator Agent
    print_info("Registering Calculator Agent...")
    calculator_manifest = {
        "agent_id": "agent:demo:calculator:1.0.0",
        "name": "Calculator Agent",
        "description": "A simple calculator agent that performs basic mathematical operations like addition, subtraction, and multiplication",
        "version": "1.0.0",
        "endpoints": {"invoke": f"{CALCULATOR_AGENT_URL}/invoke"},
        "capabilities": [
            {
                "id": "add",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number", "description": "First number"},
                        "b": {"type": "number", "description": "Second number"},
                    },
                    "required": ["a", "b"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"result": {"type": "number"}},
                },
                "auth_type": {"type": "public"},
            },
            {
                "id": "subtract",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number", "description": "First number"},
                        "b": {"type": "number", "description": "Second number"},
                    },
                    "required": ["a", "b"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"result": {"type": "number"}},
                },
                "auth_type": {"type": "public"},
            },
            {
                "id": "multiply",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number", "description": "First number"},
                        "b": {"type": "number", "description": "Second number"},
                    },
                    "required": ["a", "b"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"result": {"type": "number"}},
                },
                "auth_type": {"type": "public"},
            },
        ],
        "tags": ["math", "calculator", "arithmetic"],
        "trust": {"verification": "self-signed"},
    }

    registered_agents["calculator"] = register_or_get_agent(
        client, headers, calculator_manifest, "Calculator Agent"
    )

    # Register Text Processor Agent
    print_info("Registering Text Processor Agent...")
    text_processor_manifest = {
        "agent_id": "agent:demo:text-processor:1.0.0",
        "name": "Text Processor Agent",
        "description": "A text processing agent that can convert text to uppercase, lowercase, and reverse strings",
        "version": "1.0.0",
        "endpoints": {"invoke": f"{TEXT_PROCESSOR_AGENT_URL}/invoke"},
        "capabilities": [
            {
                "id": "uppercase",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to convert"}
                    },
                    "required": ["text"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
                "auth_type": {"type": "public"},
            },
            {
                "id": "lowercase",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to convert"}
                    },
                    "required": ["text"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
                "auth_type": {"type": "public"},
            },
            {
                "id": "reverse",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to reverse"}
                    },
                    "required": ["text"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
                "auth_type": {"type": "public"},
            },
        ],
        "tags": ["text", "processing", "string", "nlp"],
        "trust": {"verification": "self-signed"},
    }

    registered_agents["text_processor"] = register_or_get_agent(
        client, headers, text_processor_manifest, "Text Processor Agent"
    )

    # Register Weather Agent
    print_info("Registering Weather Agent...")
    weather_manifest = {
        "agent_id": "agent:demo:weather:1.0.0",
        "name": "Weather Agent",
        "description": "A weather agent that provides weather information for cities",
        "version": "1.0.0",
        "endpoints": {"invoke": f"{WEATHER_AGENT_URL}/invoke"},
        "capabilities": [
            {
                "id": "get_weather",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name"}
                    },
                    "required": ["city"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "temperature": {"type": "number"},
                        "condition": {"type": "string"},
                        "humidity": {"type": "number"},
                        "unit": {"type": "string"},
                    },
                },
                "auth_type": {"type": "public"},
            }
        ],
        "tags": ["weather", "forecast", "city"],
        "trust": {"verification": "self-signed"},
    }

    registered_agents["weather"] = register_or_get_agent(
        client, headers, weather_manifest, "Weather Agent"
    )

    print_success("All agents registered successfully!")
    return registered_agents


# Step 4: Discover Agents
def step4_discover_agents(client: httpx.Client, api_key: str):
    """Demonstrate agent discovery."""
    print_step(4, "Discovering Agents")

    headers = {"X-API-Key": api_key}

    # Discovery query 1: Math operations
    print_info("Query: 'I need to do some math calculations'")
    response = client.get(
        f"{BASE_URL}/registry/discover",
        params={"query": "I need to do some math calculations", "limit": 5},
        headers=headers,
    )
    response.raise_for_status()
    agents = response.json()
    print_success(f"Found {len(agents)} agent(s)")
    for agent in agents:
        print(f"  - {agent['name']} ({agent['agent_id']})")

    # Discovery query 2: Text processing
    print_info("\nQuery: 'I want to process some text'")
    response = client.get(
        f"{BASE_URL}/registry/discover",
        params={"query": "I want to process some text", "limit": 5},
        headers=headers,
    )
    response.raise_for_status()
    agents = response.json()
    print_success(f"Found {len(agents)} agent(s)")
    for agent in agents:
        print(f"  - {agent['name']} ({agent['agent_id']})")

    # Discovery query 3: Weather
    print_info("\nQuery: 'What's the weather like?'")
    response = client.get(
        f"{BASE_URL}/registry/discover",
        params={"query": "What's the weather like?", "limit": 5},
        headers=headers,
    )
    response.raise_for_status()
    agents = response.json()
    print_success(f"Found {len(agents)} agent(s)")
    for agent in agents:
        print(f"  - {agent['name']} ({agent['agent_id']})")

    return agents


# Step 5: Invoke Agents
def step5_invoke_agents(
    client: httpx.Client, api_key: str, registered_agents: Dict[str, str]
):
    """Invoke various agent capabilities."""
    print_step(5, "Invoking Agents")

    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    # Invoke Calculator: Add
    print_info("Invoking Calculator Agent - Add operation")
    add_response = client.post(
        f"{BASE_URL}/broker/invoke",
        json={
            "agent_id": registered_agents["calculator"],
            "capability_id": "add",
            "input": {"a": 15, "b": 27},
        },
        headers=headers,
    )
    add_response.raise_for_status()
    add_result = add_response.json()
    print_success(f"Result: {add_result.get('data', {}).get('result', 'N/A')}")
    print_info(f"Latency: {add_result.get('latency_ms', 0)}ms")

    # Invoke Calculator: Multiply
    print_info("\nInvoking Calculator Agent - Multiply operation")
    multiply_response = client.post(
        f"{BASE_URL}/broker/invoke",
        json={
            "agent_id": registered_agents["calculator"],
            "capability_id": "multiply",
            "input": {"a": 6, "b": 7},
        },
        headers=headers,
    )
    multiply_response.raise_for_status()
    multiply_result = multiply_response.json()
    print_success(f"Result: {multiply_result.get('data', {}).get('result', 'N/A')}")
    print_info(f"Latency: {multiply_result.get('latency_ms', 0)}ms")

    # Invoke Text Processor: Uppercase
    print_info("\nInvoking Text Processor Agent - Uppercase")
    uppercase_response = client.post(
        f"{BASE_URL}/broker/invoke",
        json={
            "agent_id": registered_agents["text_processor"],
            "capability_id": "uppercase",
            "input": {"text": "hello intuno!"},
        },
        headers=headers,
    )
    uppercase_response.raise_for_status()
    uppercase_result = uppercase_response.json()
    print_success(f"Result: {uppercase_result.get('data', {}).get('result', 'N/A')}")
    print_info(f"Latency: {uppercase_result.get('latency_ms', 0)}ms")

    # Invoke Text Processor: Reverse
    print_info("\nInvoking Text Processor Agent - Reverse")
    reverse_response = client.post(
        f"{BASE_URL}/broker/invoke",
        json={
            "agent_id": registered_agents["text_processor"],
            "capability_id": "reverse",
            "input": {"text": "Intuno"},
        },
        headers=headers,
    )
    reverse_response.raise_for_status()
    reverse_result = reverse_response.json()
    print_success(f"Result: {reverse_result.get('data', {}).get('result', 'N/A')}")
    print_info(f"Latency: {reverse_result.get('latency_ms', 0)}ms")

    # Invoke Weather Agent
    print_info("\nInvoking Weather Agent - Get Weather")
    weather_response = client.post(
        f"{BASE_URL}/broker/invoke",
        json={
            "agent_id": registered_agents["weather"],
            "capability_id": "get_weather",
            "input": {"city": "Paris"},
        },
        headers=headers,
    )
    weather_response.raise_for_status()
    weather_result = weather_response.json()
    print_success("Weather data retrieved:")
    print_result(weather_result.get("data", {}))
    print_info(f"Latency: {weather_result.get('latency_ms', 0)}ms")

    print_success("\nAll invocations completed successfully!")


def main():
    """Run the complete demo workflow."""
    print("\n" + "=" * 60)
    print("INTUNO DEMO - Agent Registration, Discovery & Invocation")
    print("=" * 60)

    # Check if main server is running
    try:
        response = httpx.get(f"{BASE_URL}/health", timeout=5.0)
        if response.status_code != 200:
            print(f"❌ Main server at {BASE_URL} is not responding correctly")
            return
    except Exception as e:
        print(f"❌ Cannot connect to main server at {BASE_URL}")
        print(f"   Error: {e}")
        print("\n   Please make sure the main Intuno server is running:")
        print("   uvicorn src.main:app --reload")
        return

    # Check if agent servers are running
    agent_servers = [
        ("Calculator", CALCULATOR_AGENT_URL),
        ("Text Processor", TEXT_PROCESSOR_AGENT_URL),
        ("Weather", WEATHER_AGENT_URL),
    ]

    for name, url in agent_servers:
        try:
            response = httpx.get(f"{url}/health", timeout=2.0)
            if response.status_code != 200:
                print(f"❌ {name} agent at {url} is not responding correctly")
                return
        except Exception as e:
            print(f"❌ Cannot connect to {name} agent at {url}")
            print(f"   Error: {e}")
            print("\n   Please start the agent server:")
            print(f"   python demo/agents/{name.lower().replace(' ', '_')}_agent.py")
            return

    print_success("All services are running!")

    # Run the demo steps
    with httpx.Client(timeout=30.0) as client:
        try:
            # Step 1: Create account
            account_info = step1_create_account(client)

            # Step 2: Create API key
            api_key = step2_create_api_key(
                client, account_info["email"], account_info["password"]
            )

            # Step 3: Register agents
            registered_agents = step3_register_agents(client, api_key)

            # Small delay to ensure embeddings are generated
            print_info("\nWaiting a moment for embeddings to be generated...")
            time.sleep(2)

            # Step 4: Discover agents
            step4_discover_agents(client, api_key)

            # Step 5: Invoke agents
            step5_invoke_agents(client, api_key, registered_agents)

            print("\n" + "=" * 60)
            print("DEMO COMPLETED SUCCESSFULLY! 🎉")
            print("=" * 60)
            print("\nThis demo showcased:")
            print("  ✅ Easy account creation")
            print("  ✅ Simple API key generation")
            print("  ✅ Straightforward agent registration")
            print("  ✅ Powerful semantic discovery")
            print("  ✅ Seamless agent invocation")
            print("\nIntuno makes it easy to register, discover, and invoke any agent!")

        except httpx.HTTPStatusError as e:
            print(f"\n❌ HTTP Error: {e.response.status_code}")
            print(f"   Response: {e.response.text}")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    main()
