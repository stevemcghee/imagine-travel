#!/bin/bash

# Deploy to Cloud Run
# This command builds the container using the Dockerfile in the current directory
# and deploys it to Cloud Run.

echo "Deploying Travel Memory Architect to Cloud Run..."

gcloud run deploy travel-memory-architect \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated

echo "Deployment initiated. If this is your first time, you may be prompted to enable APIs."
echo "IMPORTANT: After deployment, don't forget to set your environment variables (OPENAI_API_KEY, GOOGLE_API_KEY) in the Cloud Run console or using 'gcloud run services update'."
