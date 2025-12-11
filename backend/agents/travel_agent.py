import json
import wikipedia
from adk.core import SequentialWorkflow, Step, LoopStep, Context
from agents.mcp_client import GoogleMapsMCP
from utils import llm_completion, generate_image

# --- Tool Implementations ---

def step_grounding(context: Context):
    query = context.get("initial_input")
    
    # Extract location keyword using LLM
    extraction_prompt = f"Extract the main real-world location to search for on Google Maps from this query: '{query}'. Return just the location name."
    search_term = llm_completion(extraction_prompt, system_prompt="You are a helpful assistant.", model="gemini-2.0-flash-exp")
    context.logger(f"  > Extracted Location: {search_term}")
    
    mcp = GoogleMapsMCP()
    results = mcp.search_places(search_term)
    
    if not results:
        # Fallback to original query
        context.logger(f"  > No results for extracted term, trying original query.")
        results = mcp.search_places(query)
        
    if not results:
        raise Exception(f"No places found for {query}")
    
    # Pick the first result
    place = results[0]
    context.set("place_data", place.model_dump())
    return place.model_dump()

def step_research(context: Context):
    place_data = context.get("place_data")
    name = place_data["name"]
    try:
        # Get a short summary
        summary = wikipedia.summary(name, sentences=3)
    except wikipedia.exceptions.PageError:
        summary = "No historical data found."
    except wikipedia.exceptions.DisambiguationError as e:
        summary = wikipedia.summary(e.options[0], sentences=3)
        
    context.set("history_data", summary)
    return summary

def step_drafting_action(context: Context):
    # This action generates the journal entry
    place = context.get("place_data")
    history = context.get("history_data")
    iteration_notes = context.get("draft_feedback") or ""
    
    prompt = f"""
    Write a short, nostalgic travel journal entry (max 100 words) about visiting {place['name']}.
    
    Facts to include:
    - Address: {place['address']}
    - History: {history}
    
    Style: Emotional, personal, vivid.
    
    {iteration_notes}
    """
    
    draft = llm_completion(prompt, system_prompt="You are a travel writer.")
    context.set("current_draft", draft)
    return draft

def step_drafting_condition(context: Context, draft: str) -> bool:
    # 1. Vibe Check
    prompt_vibe = f"""
    Rate the following travel journal entry on a scale of 1-10 for "Nostalgic Vibe".
    Format: just the number.
    
    Entry: "{draft}"
    """
    score_str = llm_completion(prompt_vibe, system_prompt="You are an editor.").strip()
    try:
        score = int(''.join(filter(str.isdigit, score_str)))
    except:
        score = 5
    
    context.logger(f"  > Vibe Score: {score}/10")
    
    if score < 7:
        context.set("draft_feedback", "Critique: Make it more emotional and less encyclopedic.")
        return False

    # 2. Fact Check (Text Only)
    place = context.get("place_data")
    user_query = context.get("initial_input")
    
    prompt_judge = f"""
    You are a Fact-Checking Judge.
    
    User Query: "{user_query}"
    Original Data: {place}
    Journal Entry: "{draft}"
    
    Evaluate:
    1. Does the story accurately reflect the location's address/name?
    2. Is the story consistent with the history provided and the User's Query?
    3. Are there any hallucinations (claims not in data or query)?
    4. Does it include all the elemnts of the memory provided by the user?
    
    Return a JSON object: {{ "pass": bool, "reason": str, "score": int (from 1 to 10) }}
    """
    
    verdict_str = llm_completion(prompt_judge, system_prompt="You are a strict judge.", model="gemini-2.0-flash-exp")
    if "```json" in verdict_str:
        verdict_str = verdict_str.split("```json")[1].split("```")[0]
        
    try:
        result = json.loads(verdict_str)
    except:
        result = {"pass": False, "reason": "Failed to parse judge output", "score": 0}
    
    context.logger(f"  > Fact Score: {result.get('score')}/10 - {result.get('reason')}")
    # We don't save judge_result here to avoid overwriting the final image-aware judge, 
    # but we use it for control flow.
    
    if not result.get("pass") or result.get("score") < 8:
        context.set("draft_feedback", f"Fact Check Failed: {result.get('reason')}. Please fix inaccuracies.")
        return False
        
    return True

def step_visualize(context: Context):
    draft = context.get("current_draft")
    prompt = f"A polaroid style photo representing this story: {draft}. Do not include any text or words in the image."
    image_url = generate_image(prompt)
    context.set("image_url", image_url)
    return image_url

def step_judge(context: Context):
    place = context.get("place_data")
    image_url = context.get("image_url")
    draft = context.get("current_draft")
    user_query = context.get("initial_input")
    
    prompt = f"""
    You are a Fact-Checking Judge.
    
    User Query: "{user_query}"
    Original Data: {place}
    Journal Entry: {draft}
    Generated Image URL: {image_url} (Assume the image depicts the story).
    
    Evaluate:
    1. Does the story accurately reflect the location's address/name?
    2. Is the story consistent with the history provided and the User's Query?
    
    Return a JSON object: {{ "pass": bool, "reason": str, "score": int (from 1 to 10) }}
    """
    
    verdict = llm_completion(prompt, system_prompt="You are a strict judge.", model="gemini-2.0-flash-exp")
    # Clean up json if markdown code blocks exist
    if "```json" in verdict:
        verdict = verdict.split("```json")[1].split("```")[0]
    
    try:
        result = json.loads(verdict)
    except:
        result = {"pass": False, "reason": "Failed to parse judge output", "score": 0}
        
    context.set("judge_result", result)
    return result

# --- Workflow Construction ---

def build_travel_agent() -> SequentialWorkflow:
    wf = SequentialWorkflow("TravelJournalist")
    
    wf.add_step(Step("Grounding (Google Maps)", step_grounding))
    wf.add_step(Step("Research (Wikipedia)", step_research))
    wf.add_step(LoopStep("Drafting (Writer Loop)", step_drafting_action, step_drafting_condition, max_iterations=3))
    wf.add_step(Step("Visualization (Image Gen)", step_visualize))
    wf.add_step(Step("Evaluation (LLM Judge)", step_judge))
    
    return wf
