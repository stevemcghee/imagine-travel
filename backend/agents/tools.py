from datetime import datetime
import os
from google import genai
from google.genai import types
from google.adk.tools import ToolContext
from google.cloud import storage
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams 
import google.auth
from . import config

MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY') or os.getenv('MAPS_API_KEY', 'no_api_found')
MAPS_MCP_URL = "https://mapstools.googleapis.com/mcp" 

def get_maps_mcp_toolset():
    masked_key = MAPS_API_KEY[:4] + "..." + MAPS_API_KEY[-4:] if len(MAPS_API_KEY) > 8 else "INVALID/SHORT"
    print(f"DEBUG: Configuring MCP Toolset with API Key: {masked_key}")
    if MAPS_API_KEY == 'no_api_found':
        print("CRITICAL WARNING: MAPS_API_KEY not found in environment variables!")

    headers = {
        "X-Goog-Api-Key": MAPS_API_KEY
    }
    print(f"DEBUG: MCP Headers: {headers}")

    tools = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=MAPS_MCP_URL,
            headers=headers
        )
    )
    print("MCP Toolset configured for Streamable HTTP connection.")
    return tools

client = genai.Client(
    vertexai=True, project=os.environ.get("GOOGLE_CLOUD_PROJECT"),location="global"
)


async def generate_images(imagen_prompt: str, tool_context: ToolContext):
    try:
        response = client.models.generate_images(
            model=config.IMAGEN_MODEL,
            prompt=imagen_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="9:16",
                safety_filter_level="block_none",
            ),
        )
        generated_image_paths = []
        if response.generated_images is not None:
            for generated_image in response.generated_images:
                # Get the image bytes
                image_bytes = generated_image.image.image_bytes
                counter = str(tool_context.state.get("loop_iteration", 0))
                artifact_name = f"generated_image_" + counter + ".png"
                # call save to gcs function
                if config.GCS_BUCKET_NAME:
                    save_to_gcs(tool_context, image_bytes, artifact_name, counter)

                # Save as ADK artifact (optional, if still needed by other ADK components)
                report_artifact = types.Part.from_bytes(
                    data=image_bytes, mime_type="image/png"
                )

                await tool_context.save_artifact(artifact_name, report_artifact)
                print(f"Image also saved as ADK artifact: {artifact_name}")

                # --- Save to local frontend/public/generated_images for dev preview ---
                try:
                    local_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend/public/generated_images")
                    if os.path.exists(local_dir):
                        local_path = os.path.join(local_dir, artifact_name)
                        with open(local_path, "wb") as f:
                            f.write(image_bytes)
                        
                        # Set the state key expected by the frontend
                        tool_context.state["image_url"] = f"/generated_images/{artifact_name}"
                        print(f"Saved local image to: {local_path} and set state['image_url']")
                    else:
                        print(f"Warning: Local directory {local_dir} not found. Skipping local save.")
                except Exception as e_local:
                    print(f"Error saving local image: {e_local}")

                return {
                    "status": "success",
                    "message": f"Image generated .  ADK artifact: {artifact_name}.",
                    "artifact_name": artifact_name,
                }
        else:
            # model_dump_json might not exist or be the best way to get error details
            error_details = str(response)  # Or a more specific error field if available
            print(f"No images generated. Response: {error_details}")
            return {
                "status": "error",
                "message": f"No images generated. Response: {error_details}",
            }

    except Exception as e:

        return {"status": "error", "message": f"No images generated.  {e}"}


def save_to_gcs(tool_context: ToolContext, image_bytes, filename: str, counter: str):
    # --- Save to GCS ---
    storage_client = storage.Client()  # Initialize GCS client
    bucket_name = config.GCS_BUCKET_NAME

    unique_id = tool_context.state.get("unique_id", "")
    current_date_str = datetime.utcnow().strftime("%Y-%m-%d")
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