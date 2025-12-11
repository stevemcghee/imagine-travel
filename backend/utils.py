import os
import google.generativeai as genai
import uuid
import requests
import json
from typing import Optional

# Configure Google AI for LLM and Image Generation
# Assumes GOOGLE_API_KEY is set in environment
if "GOOGLE_API_KEY" in os.environ:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

def llm_completion(prompt: str, system_prompt: str = "You are a helpful assistant.", model: str = "gemini-2.0-flash-exp") -> str:
    """
    Simple wrapper for Gemini Chat Completion.
    """
    try:
        gemini_model = genai.GenerativeModel(model)
        chat = gemini_model.start_chat(history=[])
        response = chat.send_message(f"{system_prompt}\n{prompt}")
        return response.text.strip()
    except Exception as e:
        print(f"LLM Error (Gemini): {e}")
        return "Error generating text."

def generate_image(prompt: str) -> str:
    """
    Generates an image using Google's Imagen model via REST API and returns a local URL.
    Saves the image to frontend/public/generated_images/
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Image Gen Error: GOOGLE_API_KEY not found.")
        return "https://via.placeholder.com/1024?text=Missing+API+Key"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-generate-001:predict?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1}
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        # Parse response - format may vary, assuming standard Vertex/Gemini prediction format
        # Usually: {"predictions": [{"bytesBase64Encoded": "..."}]}
        result = response.json()
        
        # Check for predictions
        if "predictions" not in result or not result["predictions"]:
            print(f"Image Gen Error: No predictions in response: {result}")
            return "https://via.placeholder.com/1024?text=No+Predictions"
            
        b64_image = result["predictions"][0]["bytesBase64Encoded"]
        
        # Decode and save
        import base64
        image_data = base64.b64decode(b64_image)
        
        # Ensure output directory exists
        output_dir = os.path.join(os.path.dirname(__file__), "../frontend/public/generated_images")
        os.makedirs(output_dir, exist_ok=True)
        
        # Save the first image with a unique name
        filename = f"{uuid.uuid4()}.png"
        file_path = os.path.join(output_dir, filename)
        
        with open(file_path, "wb") as f:
            f.write(image_data)
        
        # Return the URL path relative to the frontend public folder
        return f"/generated_images/{filename}"
        
    except Exception as e:
        print(f"Image Gen Error (Google REST): {e}")
        if 'response' in locals():
            print(f"Response Content: {response.text}")
        return "https://via.placeholder.com/1024?text=Image+Generation+Error"
