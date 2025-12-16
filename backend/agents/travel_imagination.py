# Part of agent.py --> Follow https://google.github.io/adk-docs/get-started/quickstart/ to learn the setup

import logging
import os
import wikipedia
from dotenv import load_dotenv
from opentelemetry import trace

from google.adk.agents import LoopAgent, LlmAgent, SequentialAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.auth import AuthCredential, AuthCredentialTypes
from fastapi.openapi.models import APIKey, APIKeyIn

# Import tools and config
from . import tools
from . import config

# --- Constants ---
APP_NAME = "travel_imagination_app"
MODEL = config.GENAI_MODEL

# State Keys
STATE_LOCATION = "place_data"
STATE_HISTORY = "history_data"
STATE_CURRENT_DOC = "current_draft"
STATE_CRITICISM = "draft_feedback"
STATE_IMAGE_URL = "image_output" # Tool output will be stored here
STATE_JUDGE_RESULT = "judge_result"

COMPLETION_PHRASE = "COMPLETE"

# Setup logging
logging.basicConfig(level=logging.INFO)
# Load environment variables from .env file in the project root.
# Ensure MAPS_API_KEY is set in your project's root .env file.
load_dotenv()

# Setup Tracer
tracer = trace.get_tracer(__name__)

# --- Tools Setup ---
maps_toolset = tools.get_maps_mcp_toolset()
generate_images = tools.generate_images

def exit_loop(tool_context: ToolContext):
    """Call this function ONLY when the critique indicates no further changes are needed, signaling the iterative process should end."""
    print(f"  [Tool Call] exit_loop triggered by {tool_context.agent_name}")
    tool_context.actions.escalate = True
    tool_context.state["refinement_complete"] = True  # Explicitly set a flag in state
    return {}

@tracer.start_as_current_span("research_location_tool")
def research_location(location: str) -> str:
    """Fetch a brief summary about the location from Wikipedia.
    
    Args:
        location: The name of the location to research.
    """
    try:
        # Simple heuristic to handle dictionaries if passed as string representation
        if isinstance(location, dict) and "name" in location:
            location = location["name"]
            
        summary = wikipedia.summary(location, sentences=3)
        return summary
    except Exception as e:
        print(f"  [Research Error] Could not fetch info for {location}: {e}")
        return "No additional historical information found."

# --- Agent Definitions ---

# STEP 1: Grounding (Google Maps)
location_grounder = LlmAgent(
    name="LocationGrounder",
    model=MODEL,
    instruction=f"""
    You are a Travel Location Expert AI.
    
    **User Query:** {{initial_input}}

    Your Goal:
    1. Extract the main real-world location to search for from the query.
    2. Use the 'search_places' tool (from maps_toolset) to find details about this location.
    3. From the tool's response, carefully extract the place's **best available name** (e.g., from 'displayName.text' or 'place_name'), its **most complete formatted address** (e.g., from 'formattedAddress' or by combining address components), its **location coordinates** (latitude, longitude), and **Google Maps links**. Ensure `place_name` and `address` are always provided as non-null, complete strings. If a single 'formattedAddress' isn't available, combine components (street, city, state, country) to form a coherent address string.
    4. Return these details as a flat JSON object with keys like `place_name`, `address`, `location` (object), and `google_maps_links` (object).
    """,
    tools=[maps_toolset],
    output_key=STATE_LOCATION
)

# STEP 2: Research (Wikipedia)
fact_finder = LlmAgent(
    name="FactFinder",
    model=MODEL,
    instruction=f"""
    You are a Historian and Researcher.
    
    **Location Data:** {{{STATE_LOCATION}}}
    
    Your Goal:
    1. Identify the name of the location from the data.
    2. Use the 'research_location' tool to find a historical summary or interesting facts about it.
    3. Return the summary text.
    """,
    tools=[research_location],
    output_key=STATE_HISTORY
)

# STEP 3: Drafting (Initial Writer)
drafter = LlmAgent(
    name="InitialWriter",
    model=MODEL,
    generate_content_config={"temperature": 1.0},
    instruction=f"""
    You are a Travel Writer.
    
    **Location:** {{{STATE_LOCATION}}}
    **History:** {{{STATE_HISTORY}}}
    
    Your Goal:
    Write a short, nostalgic travel journal entry (max 100 words) about visiting this location.
    
    Style: Emotional, personal, vivid.
    Include specific details from the Location (address/name) and History.
    
    Output *only* the story/journal entry text.
    """,
    output_key=STATE_CURRENT_DOC
)

# STEP 4: Refinement Loop (Critic & Refiner)
critic = LlmAgent(
    name="Critic",
    model=MODEL,
    instruction=f"""
    You are an Editor.
    
    **Current Draft:** {{{STATE_CURRENT_DOC}}}
    **Location:** {{{STATE_LOCATION}}}
    **History:** {{{STATE_HISTORY}}}
    
    Your Goal:
    1. Rate the draft for "Nostalgic Vibe" (1-10).
    2. Check if it factually aligns with the Location and History.
    
    Criteria:
    - Vibe Score should be >= 7.
    - Must be factually accurate.
    
    Output:
    IF the draft is excellent (Score >= 7 AND Accurate):
        Respond *exactly* with the phrase "{COMPLETION_PHRASE}".
    ELSE:
        Provide specific, constructive feedback on how to improve the vibe or fix facts.
        Do not output the score number alone, explain the critique.
    """,
    output_key=STATE_CRITICISM
)

# 4b. Refiner
refiner = LlmAgent(
    name="Refiner",
    model=MODEL,
    generate_content_config={"temperature": 1.0},
    instruction=f"""
    You are a Creative Writing Assistant.
    
    **Current Draft:** {{{STATE_CURRENT_DOC}}}
    **Critique:** {{{STATE_CRITICISM}}}
    
    Your Task:
    Analyze the 'Critique'.
    
    IF the critique is *exactly* "{COMPLETION_PHRASE}":
        tool_context.state[STATE_CRITICISM] = COMPLETION_PHRASE # Explicitly set state
        You MUST call the 'exit_loop' function. Do not output any text.
        
    ELSE (the critique contains feedback):
        Rewrite the 'Current Draft' incorporating the feedback.
        Make it more emotional, vivid, or factually correct as requested.
        Output *only* the refined draft text.
    """,
    tools=[exit_loop],
    output_key=STATE_CURRENT_DOC
)

refinement_loop = LoopAgent(
    name="RefinementLoop",
    sub_agents=[critic, refiner],
    max_iterations=10
)

# STEP 5: Visualization (Image Gen)
image_generation_agent = LlmAgent(
    name="ImageGenerator",
    model=MODEL,
    # output_key=STATE_IMAGE_URL # Removed as tool directly updates state["image_url"]
    instruction=f"""
    You are an Artist.
    
    **Story:** {{{STATE_CURRENT_DOC}}}
    
    Your Goal:
    1. Create a descriptive prompt for a polaroid-style photo that represents this story.
    2. The prompt should specify "polaroid style" and "no text".
    3. Call the 'generate_images' tool with this prompt, ensuring the prompt is simple, e.g., "A simple abstract image of coffee in Paris, polaroid style, no text."
    """,
    tools=[generate_images]
) 

# STEP 6: Evaluation (Judge)
judge_agent = LlmAgent(
    name="Judge",
    model=MODEL,
    instruction=f"""
    You are a Fact-Checking Judge.
    
    **User Query:** {{initial_input}}
    **Original Data:** {{{STATE_LOCATION}}}
    **Journal Entry:** {{{STATE_CURRENT_DOC}}}
    **Generated Image Info:** {{image_url}}
    
    Evaluate:
    1. Does the story accurately reflect the location's address/name?
    2. Is the story consistent with the history provided and the User's Query?
    
    Return a JSON object: {{ "pass": bool, "reason": str, "score": int (1-10) }}
    """,
    output_key=STATE_JUDGE_RESULT
)


# STEP 7: Overall Pipeline
root_agent = SequentialAgent(
    name="TravelImaginationPipeline",
    sub_agents=[
        location_grounder,
        fact_finder,
        drafter,
        refinement_loop,
        image_generation_agent,
        judge_agent
    ],
    description="An agent pipeline that grounds travel imagination in real locations, drafts an initial story, iteratively refines it, and generates images."
)

@tracer.start_as_current_span("build_travel_agent")
def build_travel_agent():
    return root_agent
