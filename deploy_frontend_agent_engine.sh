#!/bin/bash

# Deploy Agent Engine and Frontend-Only Cloud Run Service

PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-"smcghee-ai-playground"}
REGION=${GOOGLE_CLOUD_REGION:-"us-central1"}

echo "Deploying to Project: $PROJECT_ID, Region: $REGION"

# 1. Deploy/Update Agent Engine
echo "--------------------------------------------------"
echo "Step 1: Deploying Vertex AI Agent Engine..."
echo "--------------------------------------------------"

# Ensure dependencies are installed for the script (if not already)
# ./backend/.venv/bin/pip install -r backend/requirements.txt # Optional check

# Run the python deployment script
./backend/.venv/bin/python deploy_reasoning_engine.py

if [ $? -ne 0 ]; then
    echo "Error: Agent Engine deployment failed."
    exit 1
fi

if [ ! -f "agent_engine_resource.txt" ]; then
    echo "Error: agent_engine_resource.txt not found. Deployment script might have failed to write it."
    exit 1
fi

RESOURCE_NAME=$(cat agent_engine_resource.txt)
echo "Agent Engine Resource Name: $RESOURCE_NAME"

# 2. Deploy Frontend-Only Cloud Run Service
echo "--------------------------------------------------"
echo "Step 2: Deploying Cloud Run Service (Frontend -> Agent Engine)..."
echo "--------------------------------------------------"

SERVICE_NAME="imagine-travel-frontend"

gcloud run deploy $SERVICE_NAME \
  --source . \
  --project $PROJECT_ID \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars FRONTEND_STATIC_PATH=/app/static,USE_GCP_EXPORTER=true,OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true,OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true,ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false,AGENT_ENGINE_RESOURCE_NAME=$RESOURCE_NAME

echo "--------------------------------------------------"
echo "Deployment Complete!"
echo "Frontend Service: $SERVICE_NAME"
echo "Agent Engine: $RESOURCE_NAME"
echo "--------------------------------------------------"
echo "IMPORTANT: Ensure your Cloud Run service has secrets configured if needed (though Agent Engine handles the backend logic, the Cloud Run proxy might not need them unless it does local ops)."
