from datetime import datetime, UTC
import os
import logging
from google import genai
from google.genai import types
from google.adk.tools import ToolContext
from google.cloud import storage
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams 
import google.auth
from . import config

# Setup logging
logger = logging.getLogger(__name__)

MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY') or os.getenv('MAPS_API_KEY', 'no_api_found')
MAPS_MCP_URL = "https://mapstools.googleapis.com/mcp" 

def get_maps_mcp_toolset():
    masked_key = MAPS_API_KEY[:4] + "..." + MAPS_API_KEY[-4:] if len(MAPS_API_KEY) > 8 else "INVALID/SHORT"
    logger.debug(f"Configuring MCP Toolset with API Key: {masked_key}")
    if MAPS_API_KEY == 'no_api_found':
        logger.critical("CRITICAL WARNING: MAPS_API_KEY not found in environment variables!")

    headers = {
        "X-Goog-Api-Key": MAPS_API_KEY
    }
    logger.debug(f"MCP Headers: {headers}")

    tools = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=MAPS_MCP_URL,
            headers=headers
        )
    )
    logger.info("MCP Toolset configured for Streamable HTTP connection.")
    return tools

async def generate_images(imagen_prompt: str, tool_context: ToolContext):
    logger.debug(f"FRONTEND_STATIC_PATH env var: {os.getenv('FRONTEND_STATIC_PATH')}")
    genai_client = genai.Client(
        vertexai=True, project=os.environ.get("GOOGLE_CLOUD_PROJECT"), location="global"
    )
    try:
        logger.debug(f"Sending Imagen prompt: {imagen_prompt}")
        config_obj = types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="9:16",
            # Removed safety_filter_level due to allowlisting requirement/invalid value.
        )
        logger.debug(f"Sending Imagen config: {config_obj}")
        
        response = genai_client.models.generate_images(
            model=config.IMAGEN_MODEL,
            prompt=imagen_prompt,
            config=config_obj,
        )
        
        logger.debug(f"config.GCS_BUCKET_NAME: {config.GCS_BUCKET_NAME} (type: {type(config.GCS_BUCKET_NAME)})")
        generated_image_paths = []
        if bool(config.GCS_BUCKET_NAME):
            for generated_image in response.generated_images:
                # Get the image bytes
                image_bytes = generated_image.image.image_bytes
                counter = str(tool_context.state.get("loop_iteration", 0))
                artifact_name = f"generated_image_" + counter + ".png"
                # call save to gcs function
                save_to_gcs(tool_context, image_bytes, artifact_name, counter)

                # Save as ADK artifact (optional, if still needed by other ADK components)
                report_artifact = types.Part.from_bytes(
                    data=image_bytes, mime_type="image/png"
                )

                await tool_context.save_artifact(artifact_name, report_artifact)
                logger.info(f"Image also saved as ADK artifact: {artifact_name}")

                # --- Save to local frontend/public/generated_images for dev/preview ---
                try:
                    local_dir = get_local_image_dir()

                    # Ensure directory exists
                    if not os.path.exists(local_dir):
                        os.makedirs(local_dir)

                    local_path = os.path.join(local_dir, artifact_name)
                    with open(local_path, "wb") as f:
                        f.write(image_bytes)
                    
                    # Set the state key expected by the frontend
                    tool_context.state["image_url"] = f"/generated_images/{artifact_name}"
                    logger.info(f"Saved local image to: {local_path} and set state['image_url']")
                except Exception as e_local:
                    logger.error(f"Error saving local image: {e_local}")

                return {
                    "status": "success",
                    "message": f"Image generated .  ADK artifact: {artifact_name}.",
                    "artifact_name": artifact_name,
                }
        else:
            # If GCS_BUCKET_NAME is not set, we still process the generated images (if any) locally
            if response.generated_images is not None:
                for generated_image in response.generated_images:
                    image_bytes = generated_image.image.image_bytes
                    counter = str(tool_context.state.get("loop_iteration", 0))
                    artifact_name = f"generated_image_" + counter + ".png"

                    report_artifact = types.Part.from_bytes(
                        data=image_bytes, mime_type="image/png"
                    )
                    await tool_context.save_artifact(artifact_name, report_artifact)
                    logger.info(f"Image also saved as ADK artifact: {artifact_name}")

                    try:
                        local_dir = get_local_image_dir()

                        # Ensure directory exists
                        if not os.path.exists(local_dir):
                            os.makedirs(local_dir)

                        local_path = os.path.join(local_dir, artifact_name)
                        with open(local_path, "wb") as f:
                            f.write(image_bytes)
                        tool_context.state["image_url"] = f"/generated_images/{artifact_name}"
                        logger.info(f"Saved local image to: {local_path} and set state['image_url']")
                    except Exception as e_local:
                        logger.error(f"Error saving local image: {e_local}")
                
                return {
                    "status": "success",
                    "message": f"Image generated. ADK artifact: {artifact_name}. (No GCS)",
                    "artifact_name": artifact_name,
                }
            else:
                error_details = response.error or str(response) # Try to get specific error or full response
                logger.error(f"No images generated. Response: {error_details}")
                return {
                    "status": "error",
                    "message": f"No images generated. Response: {error_details}",
                }

    except Exception as e:
        import traceback
        logger.error(f"Image generation failed: {e}")
        traceback.print_exc() # Print full traceback for unexpected errors
        return {"status": "error", "message": f"Image generation failed: {e}"}

def save_to_gcs(tool_context: ToolContext, image_bytes, filename: str, counter: str):
    # --- Save to GCS ---
    storage_client = storage.Client()  # Initialize GCS client
    bucket_name = config.GCS_BUCKET_NAME

    unique_id = tool_context.state.get("unique_id", "")
    current_date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    unique_filename = filename
    gcs_blob_name = f"{current_date_str}/{unique_id}/{unique_filename}"

    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(gcs_blob_name)

    try:
        blob.upload_from_string(image_bytes, content_type="image/png")
        gcs_uri = f"gs://{bucket_name}/{gcs_blob_name}"

        # Store GCS URI in session context
        # Store GCS URI in session context
        tool_context.state["generated_image_gcs_uri_" + counter] = gcs_uri

    except Exception as e_gcs:

        # Decide if this is a fatal error for the tool
        return {
            "status": "error",
            "message": f"Image generated but failed to upload to GCS: {e_gcs}",
        }
        # --- End Save to GCS ---

def get_local_image_dir():
    """Determines the correct local directory for saving generated images."""
    # 1. Check environment variable (Production/Cloud Run best practice)
    static_path = os.getenv("FRONTEND_STATIC_PATH")
    if static_path:
        return os.path.join(static_path, "generated_images")
    
    # 2. Check standard container path (Fallback for Cloud Run/Docker)
    if os.path.exists("/app/static"):
        return os.path.join("/app/static", "generated_images")
    
    # 3. Fallback to relative path (Local Development)
    # backend/agents/tools.py -> backend/agents -> backend -> project_root -> frontend/public/generated_images
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "frontend/public/generated_images")