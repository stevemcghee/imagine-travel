# Travel Memory Architect

## Overview

The **Travel Memory Architect** is an AI-powered agentic application that transforms your raw travel memories (e.g., "I went to Tokyo and had sushi") into rich, vivid journal entries. It combines real-world grounding, historical context, and creative generation to build a cohesive story, complete with a visual memory and a fact-checked verdict.

This project demonstrates a sophisticated **Sequential Workflow** with an embedded **Feedback Loop**, built using a custom **Agent Development Kit (ADK)**. It orchestrates multiple external tools to verify, enrich, and visualize your experience.

## Goals

1.  **Grounding**: Anchor user memories to real-world locations using Google Maps.
2.  **Enrichment**: Augment stories with historical facts using Wikipedia.
3.  **Creative Drafting**: Generate high-quality, evocative journal entries using an LLM.
4.  **Visualization**: Create a consistent visual memory (image) representing the story.
5.  **Quality Assurance**: Use an LLM Judge to fact-check the generated content against the original data, iterating on the draft if inaccuracies are found.

## Tools and APIs Used

This application integrates **3 distinct external APIs**:

1.  **Google Maps Platform**:
    *   **Places API**: Used by the agent to find the exact location, address, and details of the user's memory (via `GoogleMapsMCP`).
    *   **Maps Embed API**: Used by the frontend to display an interactive map of the location.
2.  **Wikipedia API**: Used to fetch historical context and summaries about the location.
3.  **Google Gemini API**:
    *   **Gemini 2.0 Flash**: Powers the LLM for drafting the journal, judging the content, and extracting location keywords.
    *   **Imagen 4.0**: Generates the "polaroid style" visual representation of the memory.

## Project Structure

-   `backend/`: Python FastAPI backend.
    -   `adk/`: **Agent Development Kit**. A lightweight framework for building sequential and looping agent workflows.
    -   `agents/`: Contains the specific agent logic (`travel_agent.py`) and tool integrations (`mcp_client.py`).
    -   `server.py`: The FastAPI server handling WebSocket connections and agent execution.
    -   `utils.py`: Helpers for LLM completion and Image generation.
-   `frontend/`: React/Vite frontend.
    -   `src/App.jsx`: Main UI logic, handling the WebSocket stream and layout.
    -   `src/components/`: Reusable UI components like `LogPane`.

## How to Build and Run

### Prerequisites

-   **Python 3.9+** (with `pip`)
-   **Node.js** (LTS recommended) and `npm`
-   **API Keys**:
    -   **Google Maps API Key**: Must have **Places API** and **Maps Embed API** enabled.
    -   **Google Gemini API Key**: For accessing Gemini 2.0 and Imagen models.

### 1. Setup Environment Variables

Create a `.env` file in the root directory (you can copy `.env.template` if it exists, or create new):

```bash
touch .env
```

Add your keys to `.env`. Note that `VITE_GOOGLE_MAPS_API_KEY` is required for the frontend map and is usually the same as your backend key.

```env
GOOGLE_MAPS_API_KEY=your_google_maps_key
GOOGLE_API_KEY=your_gemini_api_key
VITE_GOOGLE_MAPS_API_KEY=your_google_maps_key
```

### 2. Backend Setup

Navigate to the `backend/` directory:

```bash
cd backend
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the backend server. We provide a helper script in the root that sets up the path correctly:

```bash
# From the project root
./run_backend.sh
```

The backend will run on `http://0.0.0.0:8000`.

### 3. Frontend Setup

In a new terminal, navigate to the `frontend/` directory:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

The frontend will typically run on `http://localhost:3000` (or 3001/5173 if 3000 is taken). Check the terminal output.

### 4. Usage

1.  Open your browser to the frontend URL (e.g., `http://localhost:3000`).
2.  Enter a travel memory (e.g., "Walking across the Brooklyn Bridge at sunset with a slice of pizza").
3.  Click **Travel!**.
4.  Watch the **Execution Logs** (bottom panel) as the agent grounds your request, researches, and iteratively drafts your story.
5.  View the final result: A journal entry, an interactive map, a generated image, and a fact-check verdict.

## Deployment (Google Cloud Run)

This application is containerized and ready to be deployed to **Google Cloud Run** as a single service (Frontend + Backend).

### Prerequisites

1.  **Google Cloud Project**: You need an active GCP project.
2.  **gcloud CLI**: Installed and authenticated (`gcloud auth login`, `gcloud config set project YOUR_PROJECT_ID`).
3.  **APIs Enabled**: Cloud Run API, Cloud Build API, Artifact Registry API.

### Deployment Steps

1.  **Run the deployment script**:
    This script builds the Docker image (multi-stage build for React + Python) and deploys it to Cloud Run.

    ```bash
    ./deploy.sh
    ```

    *If the script fails due to permissions or API limits, you can manually deploy using:*
    ```bash
    gcloud run deploy travel-memory-architect --source . --platform managed --region us-central1 --allow-unauthenticated
    ```

2.  **Configure Environment Variables**:
    After the deployment finishes, the service will likely fail to run the agent logic because the API keys are missing. You must set them in the Cloud Run service configuration:

    ```bash
    gcloud run services update travel-memory-architect \
      --set-env-vars="GOOGLE_MAPS_API_KEY=your_key,GOOGLE_API_KEY=your_key" \
      --region us-central1
    ```

    *Alternatively, go to the Google Cloud Console > Cloud Run > travel-memory-architect > Edit & Deploy Variables.*

3.  **Access the App**:
    The command output will provide a Service URL (e.g., `https://travel-memory-architect-xyz-uc.a.run.app`). Open this URL in your browser.