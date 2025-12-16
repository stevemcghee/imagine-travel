import os
import asyncio
import uuid
import logging
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()
logger.info("Loaded environment variables.")

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import json
import inspect
from google.genai import types

# Import Telemetry
try:
    from otel_setup import init_telemetry
except ImportError:
    print("Warning: Could not import otel_setup. Telemetry will be disabled.")
    def init_telemetry(app, service_name): pass

# Import ADK components
try:
    # Reverting to the 'google.adk' namespace based on initial agent code structure
    from google.adk.agents.llm_agent import Agent
    from google.adk.runners import InMemoryRunner as Runner
    from google.adk.events import Event
    print("Successfully imported ADK components from google.adk.")
except ImportError as e:
    print(f"ADK Import Error in server.py: {e}. Make sure 'google-adk' is installed and the import paths are correct.")
    raise e

# Import agent builders
# Assuming agents are in a directory and have a build_<agent_name> function
from agents.travel_imagination import build_travel_agent as build_travel_agent_adk
# Add other agents here if they exist

# Agent registry
AGENT_REGISTRY = {
    "travel_agent": build_travel_agent_adk,
    # Add other agents here
}

# --- FastAPI App Setup ---
app = FastAPI(
    title="ADK API Server",
    description="API server for ADK agents",
    version="1.0.0",
)

# Initialize Telemetry
init_telemetry(app, service_name="travel-imagination-agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev, allow all. In production, restrict this.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request Models ---
class AgentQuery(BaseModel):
    query: str
    user_id: str = "default_user"
    session_id: str | None = None

class AgentRunResponse(BaseModel):
    status: str
    message: str | None = None
    final_data: dict | None = None
    history: list | None = None # For API endpoint

# --- API Endpoints ---

@app.get("/list-apps", summary="List available agents")
async def list_apps():
    """Lists all available agents that can be run."""
    return {"agents": list(AGENT_REGISTRY.keys())}

# For SSE streaming of agent events
@app.websocket("/ws/run_agent/{agent_name}")
async def websocket_endpoint(
    websocket: WebSocket,
    agent_name: str
):
    """WebSocket endpoint to run an agent and stream events."""
    await websocket.accept()
    
    if agent_name not in AGENT_REGISTRY:
        await websocket.send_json({"type": "error", "message": f"Agent '{agent_name}' not found."})
        await websocket.close()
        return

    agent_builder = AGENT_REGISTRY[agent_name]

    try:
        data = await websocket.receive_json()
        query_input = data.get("query")
        # Use provided IDs or generate defaults
        user_id = data.get("user_id", "default_ws_user")
        session_id = data.get("session_id") or str(uuid.uuid4())
        
        if not query_input:
            await websocket.send_json({"type": "error", "message": "No query provided in message."})
            return

        # Instantiate the agent and runner
        agent = agent_builder()
        runner = Runner(agent=agent, app_name="travel_imagination_app")       
        
        logger.info(f"WS ({agent_name}): Starting agent execution with query: {query_input}")

        # Explicitly create the session
        await runner.session_service.create_session(user_id=user_id, session_id=session_id, app_name="travel_imagination_app")
        
        # Construct the message object
        new_message = types.Content(role="user", parts=[types.Part.from_text(text=query_input)])
        
        final_state = {}

        # Run the agent and stream events
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=new_message, state_delta={"initial_input": query_input}):
            
            # 1. Handle State Updates
            if event.actions and event.actions.state_delta:
                state_delta = event.actions.state_delta
                final_state.update(state_delta)
                logger.info(f"WS ({agent_name}) State Update: {state_delta.keys()}")
                await websocket.send_json({"type": "state_update", "data": state_delta})
            
            # 2. Handle Errors
            if event.error_message:
                # Specific check for benign error during loop termination
                if event.error_message == "Unknown error." and final_state.get("refinement_complete"):
                    logger.info(f"WS ({agent_name}) Ignoring expected loop termination signal ('Unknown error.').")
                    continue

                logger.error(f"WS ({agent_name}) Sending Error: {event.error_message}")
                await websocket.send_json({"type": "error", "message": event.error_message})
                # Don't break immediately, maybe other events have info, but typically error ends it.
            
            # 3. Handle Logs / Content
            # Extract text from content parts if available
            log_message = ""
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        log_message += part.text
            
            if log_message:
                sender = event.author or "Agent"
                # Optionally filter out pure JSON outputs if they are just tool inputs/outputs, 
                # but for now logging everything is safer for debug.
                await websocket.send_json({"type": "log", "message": f"[{sender}]: {log_message}"})
            
            # Log tool calls
            if event.content and event.content.parts:
                 for part in event.content.parts:
                     if part.function_call:
                         sender = event.author or "Agent"
                         func_name = part.function_call.name
                         func_args = part.function_call.args
                         await websocket.send_json({"type": "log", "message": f"[{sender}]: Calling tool '{func_name}' with args: {func_args}..."})

        # 4. Send Final Result
        logger.info(f"WS ({agent_name}): Agent execution finished. Sending result.")
        
        # Retrieve full session state to ensure nothing was missed
        try:
            session = await runner.session_service.get_session(session_id=session_id, user_id=user_id, app_name="travel_imagination_app")
            if session and session.state:
                logger.info(f"WS ({agent_name}) Full Session State Keys: {session.state.keys()}")
                if "image_url" in session.state:
                    logger.info(f"WS ({agent_name}) FOUND image_url in session state: {session.state['image_url']}")
                else:
                    logger.warning(f"WS ({agent_name}) WARNING: image_url NOT found in session state.")
                final_state.update(session.state)
        except Exception as e_state:
            logger.warning(f"WS ({agent_name}) Warning: Could not retrieve full session state: {e_state}")

        logger.info(f"WS ({agent_name}) FINAL PAYLOAD TO FRONTEND: {json.dumps(final_state, default=str)}")
        await websocket.send_json({"type": "result", "data": {"final_data": final_state}})
            
    except WebSocketDisconnect:
        logger.info(f"WS ({agent_name}): Client disconnected")
    except Exception as e:
        import traceback
        logger.error(f"WS ({agent_name}) Runtime Error: {e}")
        traceback.print_exc() # Print full traceback
        try:
            await websocket.send_json({"type": "error", "message": f"An error occurred: {str(e)}"})
        except:
            pass # Ignore if connection is already closed

# Endpoint to run agent and get a single JSON response (simulating /run)
@app.post("/run/{agent_name}", response_model=AgentRunResponse, summary="Run an agent and get all events")
async def run_agent_api(
    agent_name: str,
    query_data: AgentQuery
):
    """Executes an agent and returns all generated events in a single JSON array."""
    
    if agent_name not in AGENT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")

    agent_builder = AGENT_REGISTRY[agent_name]

    logger.info(f"API ({agent_name}): Received query: {query_data.query}")
    try:
        agent = agent_builder()
        runner = Runner(agent=agent, app_name="travel_imagination_app")       
        
        # Collect all events in a list
        collected_events = []
        error_message = None
        final_state = {}
        
        session_id = query_data.session_id or str(uuid.uuid4())
        
        # Explicitly create the session
        await runner.session_service.create_session(user_id=query_data.user_id, session_id=session_id, app_name="travel_imagination_app")

        new_message = types.Content(role="user", parts=[types.Part.from_text(text=query_data.query)])

        # The runner.run method is expected to return a Context object with final state.
        # We need to collect all events from the generator.
        async_events_generator = runner.run_async(
            user_id=query_data.user_id,
            session_id=session_id,
            new_message=new_message,
            state_delta={"initial_input": query_data.query}
        )
        
        # Iterate through the events and collect them
        try:
            async for event in async_events_generator:
                # Capture state updates
                if event.actions and event.actions.state_delta:
                    final_state.update(event.actions.state_delta)
                
                # Convert event to a serializable dict for history
                # event.model_dump() is available on Pydantic models
                event_dict = event.model_dump()
                # Ensure complex types are serializable if needed (usually pydantic handles it)
                collected_events.append(event_dict)

                if event.error_message:
                    error_message = event.error_message

        except Exception as agent_ex:
            error_message = f"Agent execution failed: {str(agent_ex)}"

        if error_message:
            # If an error occurred during agent execution, return an error response
            return AgentRunResponse(status="error", message=error_message)

        # If the agent completed successfully, return the collected events
        return AgentRunResponse(status="success", final_data=final_state, history=collected_events)
        
    except ImportError as e:
        logger.error(f"API Import Error ({agent_name}): {e}. Make sure ADK components are correctly installed.")
        raise HTTPException(status_code=500, detail=f"Import Error: {e}. Please check backend setup.")
    except Exception as e:
        logger.error(f"API Runtime Error ({agent_name}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Static File Serving ---
# Mount static files (Frontend build output)
# This should be mounted last so that API routes take precedence.
# We assume the frontend build output is in a 'static' directory relative to the backend.
# If frontend is in 'frontend/dist', the path needs adjustment.
# Based on project structure, it's frontend/dist.

# Determine static directory path
possible_paths = [
    os.getenv("FRONTEND_STATIC_PATH"),
    "frontend/dist",
    "static",
    "../frontend/dist" 
]

static_dir_path = None
for path in possible_paths:
    if path and os.path.isdir(path):
        static_dir_path = path
        break

if static_dir_path is None:
    logger.warning(f"WARNING: Could not find frontend static files in any of: {possible_paths}. Frontend may not load.")
    # Fallback to avoid crash, but frontend won't work
    static_dir_path = "static" 
    # Create it if it doesn't exist to prevent crash? 
    # Better to just let it crash or warn? 
    # Starlette will crash if we pass a non-existent dir.
    # Let's create a dummy one if needed to keep the API alive? 
    # No, better to fail fast or just not mount.
else:
    logger.info(f"Mounting frontend static files from: {static_dir_path}")

# --- Main Entry Point ---
if __name__ == "__main__":
    import uvicorn
    # Use PORT env var if available (Cloud Run), else default to 8000
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting Uvicorn server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

# Mount static files (Frontend build output)
# Mount only if directory exists to avoid crash on startup
if static_dir_path and os.path.isdir(static_dir_path):
    # Explicitly mount generated images directory to avoid SPA fallback issues
    generated_images_path = os.path.join(static_dir_path, "generated_images")
    os.makedirs(generated_images_path, exist_ok=True)
    logger.info(f"Mounting generated images from: {generated_images_path}")
    app.mount("/generated_images", StaticFiles(directory=generated_images_path), name="generated_images")

    # Mount root static files (SPA)
    app.mount("/", StaticFiles(directory=static_dir_path, html=True), name="static")
else:
    logger.error("ERROR: Static files directory not found. '/' route will not serve frontend.")