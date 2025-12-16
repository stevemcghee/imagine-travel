#!/bin/bash

# Run OpenTelemetry Collector Contrib (contains googlecloud exporter)
# Maps the local config file and exposes OTLP ports.
# Mounts ~/.config/gcloud to share local gcloud credentials if available.

echo "Starting OpenTelemetry Collector..."
echo "Config: ./otel-collector-config.yaml"

# Attempt to find gcloud credentials to mount
GCLOUD_CONFIG="${HOME}/.config/gcloud"
CRED_MOUNT=""
if [ -d "$GCLOUD_CONFIG" ]; then
    CRED_MOUNT="-v ${GCLOUD_CONFIG}:/root/.config/gcloud -v ${HOME}/.config/gcloud:/root/.config/gcloud"
    echo "Mounting gcloud credentials from ${GCLOUD_CONFIG}"
fi

docker run --rm -p 4317:4317 -p 4318:4318 \
  -v "$(pwd)/otel-collector-config.yaml":/etc/otelcol-contrib/config.yaml \
  $CRED_MOUNT \
  otel/opentelemetry-collector-contrib:latest
