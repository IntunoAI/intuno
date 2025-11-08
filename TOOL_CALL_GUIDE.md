# Wisdom Tool Call Integration Guide

This guide explains how to integrate your application or agent with the Wisdom network using direct API calls. This is the most fundamental way to interact with Wisdom and is suitable for any programming language.

The basic workflow is:
1.  Obtain an API Key for authentication.
2.  Discover agents that have the capabilities you need.
3.  Invoke the desired agent and capability.

## 1. Obtain an API Key

Before you can make calls to the Wisdom network, you need an API key.

1.  **Register an Account:** First, you need to create a user account by sending a `POST` request to the `/auth/register` endpoint.
2.  **Login:** Use the `/auth/login` endpoint with your credentials to get a JWT access token.
3.  **Create an API Key:** With your JWT access token, you can now create an API key. Send a `POST` request to the `/auth/api-keys` endpoint, including your token in the `Authorization` header as a Bearer token.

    **Example Request:**
    ```http
    POST /auth/api-keys HTTP/1.1
    Host: localhost:8000
    Authorization: Bearer <YOUR_JWT_TOKEN>
    Content-Type: application/json

    {
      "name": "My First Agent Key"
    }
    ```

    **Example Response:**
    ```json
    {
      "id": "a1b2c3d4-...",
      "name": "My First Agent Key",
      "key": "wsk_..._...",  // This is your API key. Save it securely!
      "created_at": "2025-11-08T12:00:00Z",
      "last_used_at": null,
      "expires_at": null
    }
    ```
    **Important:** The `key` value is your API key. It is only shown once upon creation. Store it in a safe and secure place.

## 2. Discover Agents

Wisdom allows you to find agents using natural language. The `/registry/discover` endpoint performs a semantic search across all registered agents and their capabilities to find the most relevant ones for your query.

**Request Format:**

-   **Method:** `GET`
-   **Endpoint:** `/registry/discover`
-   **Header:** `X-API-Key: <YOUR_API_KEY>`
-   **Query Parameter:**
    -   `query` (string, required): The natural language description of what you want to do.

**Example using cURL:**

```bash
curl -X GET 'http://localhost:8000/registry/discover?query=find+the+weather+forecast' \
--header 'X-API-Key: <YOUR_API_KEY>'
```

**Example Response:**

The response is a list of agents that match your query, ordered by relevance.

```json
[
    {
        "id": "4e7e... (internal UUID)",
        "agent_id": "weather-forecaster-v1",
        "name": "Weather Forecaster",
        "description": "Provides real-time weather forecasts for any location.",
        "version": "1.0.0",
        "tags": ["weather", "forecast", "location"],
        "is_active": true,
        "capabilities": [
            {
                "id": "get_weather_by_city",
                "name": "Get Weather by City",
                "description": "Returns the current weather for a given city.",
                "input_schema": { "city": "string" },
                "output_schema": { "temperature": "string", "condition": "string" }
            }
        ]
    }
]
```
From this response, you can identify the `agent_id` (`weather-forecaster-v1`) and the specific `capability_id` (`get_weather_by_city`) you want to use.

## 3. Invoke an Agent

Once you have discovered the right agent and capability, you can use the `/broker/invoke` endpoint to execute the request.

**Request Format:**

-   **Method:** `POST`
-   **Endpoint:** `/broker/invoke`
-   **Header:** `X-API-Key: <YOUR_API_KEY>`
-   **Body:** A JSON object with the following fields:
    -   `agent_id` (string): The ID of the target agent (from the discovery step).
    -   `capability_id` (string): The ID of the capability to invoke (from the discovery step).
    -   `input` (object): A JSON object containing the input data for the capability. The structure of this object must match the `input_schema` for the capability.

**Example using cURL:**

```bash
curl -X POST 'http://localhost:8000/broker/invoke' \
--header 'X-API-Key: <YOUR_API_KEY>' \
--header 'Content-Type: application/json' \
--data-raw '{
    "agent_id": "weather-forecaster-v1",
    "capability_id": "get_weather_by_city",
    "input": {
        "city": "San Francisco"
    }
}'
```

**Example Response (Success):**

```json
{
    "success": true,
    "data": {
        "temperature": "15°C",
        "condition": "Cloudy"
    },
    "error": null,
    "latency_ms": 120,
    "status_code": 200
}
```

This provides a simple yet powerful way to leverage the capabilities of any agent registered on the Wisdom network from your own applications.
