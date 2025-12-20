#!/bin/bash

export PYTHONPATH=$PYTHONPATH:./backend

# Run uvicorn from the virtual environment
./backend/.venv/bin/python -m uvicorn backend.server:app --reload --host 0.0.0.0
