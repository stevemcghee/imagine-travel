import os
import logging
import asyncio
from typing import Optional, List, Dict, Any

import vertexai
from vertexai.preview import reasoning_engines

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

    # Define the Agent Class
class TravelAgent:
    def __init__(self, 
                 project_id: str, 
                 location: str, 
                 maps_api_key: str,
                 staging_bucket: str):
        
        self.project_id = project_id
        self.location = location
        self.maps_api_key = maps_api_key
        self.staging_bucket = staging_bucket
        
        self.agent = None
        self.runner = None
    def set_up(self):
        """
        Explicit setup method to initialize the agent.
        This can be called by Reasoning Engine upon initialization in the cloud if configured,
        or we call it lazily.
        """
        pass

    async def query(self, input_text: str, session_id: str = "default_session") -> str:
        """
        Runs the agent with the given input text.
        """
        import os
        import asyncio
        import logging
        import vertexai # Import vertexai locally on remote
        from backend.agents.travel_imagination import build_travel_agent
        from google.adk.runners import InMemoryRunner
        from google.genai import types

        # Setup logging inside the remote execution
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)

        # Initialize Vertex AI for the remote environment
        vertexai.init(project=self.project_id, location=self.location, staging_bucket=self.staging_bucket)
        # Set other env vars needed by tools that use os.getenv
        os.environ["GOOGLE_CLOUD_PROJECT"] = self.project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = self.location
        os.environ["MAPS_API_KEY"] = self.maps_api_key
        os.environ["GCS_BUCKET_NAME"] = self.staging_bucket
        os.environ["IMAGEN_MODEL"] = os.getenv("IMAGEN_MODEL", "imagen-3.0-generate-002")
        os.environ["GENAI_MODEL"] = os.getenv("GENAI_MODEL", "gemini-2.0-flash")

        if self.agent is None:
            logger.info("Initializing Travel Agent...")
            self.agent = build_travel_agent()
            self.runner = InMemoryRunner(agent=self.agent, app_name="travel_imagination_app")
            logger.info("Travel Agent initialized.")

        async def run_async():
            # Create a session
            await self.runner.session_service.create_session(
                user_id="default_user",
                session_id=session_id,
                app_name="travel_imagination_app",
                state={
                    "image_url": "No image generated yet",
                    "config_project_id": self.project_id,
                    "config_location": self.location
                }
            )
            
            new_message = types.Content(
                role="user", 
                parts=[types.Part.from_text(text=input_text)]
            )
            
            final_response = ""
            
            # Run the agent
            async for event in self.runner.run_async(
                user_id="default_user", 
                session_id=session_id, 
                new_message=new_message, 
                state_delta={"initial_input": input_text, "image_url": "No image generated yet"}
            ):
                # We can capture logs or intermediate steps here if needed
                if event.error_message:
                    logger.error(f"Agent Error: {event.error_message}")
                
                pass

            # Retrieve final state
            session = await self.runner.session_service.get_session(
                session_id=session_id, 
                user_id="default_user", 
                app_name="travel_imagination_app"
            )
            
            if session and session.state:
                 # Try to find the "journal entry"
                 story = session.state.get("current_draft", "No story generated.")
                 image_url = session.state.get("image_url", "")
                 return f"Story: {story}\n\nImage URL: {image_url}"
            
            return "Agent finished but no state returned."

        # Await the async function
        try:
            return await run_async()
        except Exception as e:
            logger.error(f"Error executing agent: {e}")
            return f"Error: {e}"


# Main deployment script
if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    
    load_dotenv("backend/.env") # Load local env vars

    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or "smcghee-ai-playground"
    LOCATION = "us-central1"
    STAGING_BUCKET = os.getenv("GCS_BUCKET_NAME") or "gs://smcghee-ai-playground-staging"
    MAPS_API_KEY = os.getenv("MAPS_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")

    if not MAPS_API_KEY:
        print("Error: MAPS_API_KEY is not set.")
        exit(1)

    print(f"Deploying to Project: {PROJECT_ID}, Location: {LOCATION}")
    print(f"Staging Bucket: {STAGING_BUCKET}")

    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)

    # Initialize the agent instance locally to verify and for pickling
    agent_instance = TravelAgent(
        project_id=PROJECT_ID,
        location=LOCATION,
        maps_api_key=MAPS_API_KEY,
        staging_bucket=STAGING_BUCKET
    )

    # Define requirements
    # Read from backend/requirements.txt
    with open("backend/requirements.txt", "r") as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    DISPLAY_NAME = "Imagine Travel Agent"

    print(f"Checking for existing Reasoning Engines with name '{DISPLAY_NAME}'...")
    try:
        existing_engines = reasoning_engines.ReasoningEngine.list(location=LOCATION)
        for engine in existing_engines:
            if engine.display_name == DISPLAY_NAME:
                print(f"Deleting existing engine: {engine.resource_name}...")
                try:
                    engine.delete()
                    print("Deleted.")
                except Exception as e:
                    print(f"Failed to delete {engine.resource_name}: {e}")
    except Exception as e:
        print(f"Warning: Failed to list/cleanup existing engines: {e}")

    print("Deploying Reasoning Engine...")
    remote_agent = reasoning_engines.ReasoningEngine.create(
        agent_instance,
        requirements=requirements,
        extra_packages=["./backend"], # Upload the backend directory
        display_name=DISPLAY_NAME,
        description="ADK-based Travel Agent",
    )
    
    print(f"Deployment Complete!")
    print(f"Reasoning Engine Name: {remote_agent.resource_name}")
    
    # Write resource name to file for the shell script to pick up
    # This file is temporary and should be ignored by git (added to .gitignore)
    with open("agent_engine_resource.txt", "w") as f:
        f.write(remote_agent.resource_name)