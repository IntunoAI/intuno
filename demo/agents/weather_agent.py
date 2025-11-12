"""
Simple Weather Agent

This agent provides weather information (with hardcoded data for demo purposes).
"""

from fastapi import FastAPI

app = FastAPI(title="Weather Agent", version="1.0.0")

# Hardcoded weather data for demo
WEATHER_DATA = {
    "paris": {"temperature": 15, "condition": "sunny", "humidity": 60},
    "london": {"temperature": 12, "condition": "cloudy", "humidity": 75},
    "new york": {"temperature": 20, "condition": "partly cloudy", "humidity": 55},
    "tokyo": {"temperature": 18, "condition": "rainy", "humidity": 80},
    "sydney": {"temperature": 22, "condition": "sunny", "humidity": 65},
}


@app.post("/invoke", response_model=dict)
async def invoke(request: dict):
    """
    Invoke endpoint that handles all capabilities.
    The broker will send requests in the format:
    {
        "capability_id": "get_weather",
        "input": {"city": "paris"}
    }
    """
    capability_id = request.get("capability_id")
    input_data = request.get("input", {})
    
    if capability_id == "get_weather":
        city = input_data.get("city", "").lower()
        weather = WEATHER_DATA.get(city, {
            "temperature": 15,
            "condition": "unknown",
            "humidity": 50
        })
        return {
            "city": city,
            "temperature": weather["temperature"],
            "condition": weather["condition"],
            "humidity": weather["humidity"],
            "unit": "celsius"
        }
    
    else:
        return {"error": f"Unknown capability: {capability_id}"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)

