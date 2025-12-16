#!/bin/bash

# Deploy to Cloud Run
# This command builds the container using the Dockerfile in the current directory
# and deploys it to Cloud Run.

echo "Deploying Imagine Travel to Cloud Run..."

gcloud run deploy imagine-travel \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars FRONTEND_STATIC_PATH=/app/static,USE_GCP_EXPORTER=true

#echo "Setting IAM policy to allow public access..."
#gcloud beta run services add-iam-policy-binding imagine-travel \
#    --region=us-central1 \
#    --member=allUsers \
#    --role=roles/run.invoker

echo "Deployment initiated. If this is your first time, you may be prompted to enable APIs."
echo "IMPORTANT: After deployment, don't forget to set your secrets (GOOGLE_API_KEY, GOOGLE_MAPS_API_KEY, VITE_GOOGLE_MAPS_API_KEY) in the Cloud Run console or using 'gcloud run services update'."
