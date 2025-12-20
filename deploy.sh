#!/bin/bash

# Deploy to Cloud Run
# This command builds the container using the Dockerfile in the current directory
# and deploys it to Cloud Run.

echo "Deploying Imagine Travel to Cloud Run..."

gcloud run deploy imagine-travel \
  --source . \
  --project smcghee-ai-playground \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars FRONTEND_STATIC_PATH=/app/static,USE_GCP_EXPORTER=true,OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true,OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true,ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false

#echo "Setting IAM policy to allow public access..."
#gcloud beta run services add-iam-policy-binding imagine-travel \
#    --region=us-central1 \
#    --member=allUsers \
#    --role=roles/run.invoker

echo "Deployment initiated. If this is your first time, you may be prompted to enable APIs."
echo "IMPORTANT: After deployment, don't forget to set your secrets (GOOGLE_API_KEY, GOOGLE_MAPS_API_KEY, VITE_GOOGLE_MAPS_API_KEY) in the Cloud Run console or using 'gcloud run services update'."
