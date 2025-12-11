import os
import asyncio
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
# from dotenv import load_dotenv

# Load env vars
# load_dotenv()

from agents.travel_agent import build_travel_agent

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For dev, allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AgentRequest(BaseModel):
    query: str

@app.websocket("/ws/run_agent")
async def websocket_endpoint(websocket: WebSocket):
    print("WS: Connection accepted")
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        query = data.get("query")
        print(f"WS: Received query: {query}")
        
        if not query:
            await websocket.send_json({"type": "error", "message": "No query provided"})
            return

        loop = asyncio.get_event_loop()
        
        def log_callback(msg):
            print(f"WS: Log callback received: {msg}")
            try:
                asyncio.run_coroutine_threadsafe(
                    websocket.send_json({"type": "log", "message": str(msg)}), 
                    loop
                )
            except Exception as e:
                print(f"WS: Error in log callback: {e}")

        print("WS: Starting agent execution...")
        agent = build_travel_agent()
        context = await asyncio.to_thread(agent.execute, query, logger=log_callback)
        print("WS: Agent execution finished")

        if context.get("error"):
            await websocket.send_json({"type": "error", "message": context.get("error")})
        else:
            result = {
                "status": "success",
                "history": context.history,
                "final_data": {
                    "place": context.get("place_data"),
                    "draft": context.get("current_draft"),
                    "image_url": context.get("image_url"),
                    "judge_verdict": context.get("judge_result")
                }
            }
            await websocket.send_json({"type": "result", "data": result})
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WS Error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass

@app.post("/api/run_agent")
async def run_agent(req: AgentRequest):
    print(f"Received request for: {req.query}")
    try:
        agent = build_travel_agent()
        context = agent.execute(req.query)
        
        # Check for errors in context
        if context.get("error"):
             raise HTTPException(status_code=500, detail=context.get("error"))
             
        return {
            "status": "success",
            "history": context.history,
            "final_data": {
                "place": context.get("place_data"),
                "draft": context.get("current_draft"),
                "image_url": context.get("image_url"),
                "judge_verdict": context.get("judge_result")
            }
        }
    except Exception as e:
        print(f"Server Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files (Frontend)
# We mount this last so that API routes take precedence
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Use PORT env var if available (Cloud Run), else 8000
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
