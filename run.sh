#!/bin/bash

echo "Running private-histogram app"

# Activate virtual environment and run the application
uv venv --allow-existing
uv pip install --upgrade syftbox
uv run python main.py
