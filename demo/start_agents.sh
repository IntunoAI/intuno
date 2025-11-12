#!/bin/bash

# Script to start all demo agent servers

echo "Starting Intuno Demo Agents..."
echo ""

# Start Calculator Agent
echo "Starting Calculator Agent on port 8001..."
python agents/calculator_agent.py &
CALC_PID=$!

# Start Text Processor Agent
echo "Starting Text Processor Agent on port 8002..."
python agents/text_processor_agent.py &
TEXT_PID=$!

# Start Weather Agent
echo "Starting Weather Agent on port 8003..."
python agents/weather_agent.py &
WEATHER_PID=$!

echo ""
echo "All agents started!"
echo "Calculator Agent PID: $CALC_PID"
echo "Text Processor Agent PID: $TEXT_PID"
echo "Weather Agent PID: $WEATHER_PID"
echo ""
echo "To stop all agents, run: kill $CALC_PID $TEXT_PID $WEATHER_PID"
echo ""
echo "Press Ctrl+C to stop this script (agents will continue running)"

# Wait for user interrupt
wait

