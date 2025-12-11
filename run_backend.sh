#!/bin/bash

export PYTHONPATH=$PYTHONPATH:./backend

# Run uvicorn
uvicorn backend.server:app --reload --host 0.0.0.0
