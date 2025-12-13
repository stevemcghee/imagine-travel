import { useState, useRef, useEffect } from 'react'
import { Plane, Map as MapIcon, Camera, Stamp, ArrowLeft, Loader2, Sparkles } from 'lucide-react'
import LogPane from './components/LogPane'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? 'http://localhost:8000' : window.location.origin);

const SAMPLE_PROMPTS = [
  "A rainy afternoon in Tokyo, drinking matcha in Shinjuku.",
  "Hiking the Grand Canyon at sunrise, the colors were unreal.",
  "Walking across the Brooklyn Bridge at sunset with a slice of pizza.",
  "Lost in the souks of Marrakech, smelling spices and mint tea."
];

// Helper to convert HTTP URL to WS URL
const getWsUrl = (url) => {
  try {
    const urlObj = new URL(url);
    urlObj.protocol = urlObj.protocol === 'https:' ? 'wss:' : 'ws:';
    urlObj.pathname = '/ws/run_agent/travel_agent';
    return urlObj.toString();
  } catch (e) {
    return 'ws://localhost:8000/ws/run_agent/travel_agent';
  }
}

// Helper to safely get the map URL regardless of casing and structure
const getMapUrl = (placeData) => {
    if (!placeData) return null;

    // Prioritize name/address for map query
    const name = placeData.place_name || placeData.name;
    const address = placeData.address;
    if (name || address) {
        const q = [name, address].filter(Boolean).join(" ");
        return `https://maps.google.com/maps?q=${encodeURIComponent(q)}&z=15&output=embed`;
    }
    
    // Fallback to coordinates for precise location if name/address not available
    if (placeData.location?.latitude && placeData.location?.longitude) {
        return `https://maps.google.com/maps?q=${placeData.location.latitude},${placeData.location.longitude}&z=15&output=embed`;
    }
    
    return null;
}

// Helper to get place name safely
const getPlaceName = (placeData) => {
    if (!placeData) return null;
    return placeData.place_name || placeData.name || placeData.place;
}


function App() {
  const [query, setQuery] = useState('')
  const [hasStarted, setHasStarted] = useState(false)
  const [loading, setLoading] = useState(false)
  
  // Separate states for progressive rendering
  const [placeData, setPlaceData] = useState(null)
  const [historyData, setHistoryData] = useState(null) // Unused in UI, but good for debug
  const [currentDraft, setCurrentDraft] = useState(null)
  const [imageUrl, setImageUrl] = useState(null)
  const [judgeResult, setJudgeResult] = useState(null) // Renamed from judge_verdict

  const [error, setError] = useState(null)
  const [logs, setLogs] = useState([])
  const wsRef = useRef(null)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!query) return

    setHasStarted(true)
    setLoading(true)
    
    // Reset all results-related states
    setPlaceData(null)
    setHistoryData(null)
    setCurrentDraft(null)
    setImageUrl(null)
    setJudgeResult(null)
    setError(null)
    setLogs([])

    // Close existing connection if any
    if (wsRef.current) {
      wsRef.current.close()
    }

    const wsUrl = getWsUrl(API_BASE_URL)
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setLogs(prev => [...prev, `[Frontend]: Sending query: "${query}"`])
      console.log(`[Frontend]: Sending query: "${query}"`);
      ws.send(JSON.stringify({ query }))
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        
        if (data.type === 'log') {
          setLogs(prev => [...prev, data.message])
          setError(null); // Clear error on new log activity
        } else if (data.type === 'state_update') { // Handle incremental state updates
            setError(null); // Clear error on state update
            const stateDelta = data.data;

            if (stateDelta.place_data) {
                let parsedPlaceData = stateDelta.place_data;
                if (typeof parsedPlaceData === 'string') {
                    try {
                        const cleanJson = parsedPlaceData.replace(/```json/g, '').replace(/```/g, '').replace(/\'/g, "'").trim();
                        parsedPlaceData = JSON.parse(cleanJson);
                        console.log("Parsed place_data object (from state_update):", parsedPlaceData);
                    } catch (e) {
                        console.error("Failed to parse place_data JSON (from state_update):", e);
                    }
                }
                setPlaceData(parsedPlaceData);
            }
            if (stateDelta.history_data) {
                setHistoryData(stateDelta.history_data);
            }
            if (stateDelta.current_draft) {
                setCurrentDraft(stateDelta.current_draft);
            }
            if (stateDelta.image_url) {
                setImageUrl(stateDelta.image_url);
            }
            if (stateDelta.judge_result) {
                let parsedJudgeResult = stateDelta.judge_result;
                 if (typeof parsedJudgeResult === 'string') {
                    try {
                        const cleanJson = parsedJudgeResult.replace(/```json/g, '').replace(/```/g, '').trim();
                        parsedJudgeResult = JSON.parse(cleanJson);
                    } catch (e) {
                        console.error("Failed to parse judge_result JSON (from state_update):", e);
                    }
                }
                setJudgeResult(parsedJudgeResult);
            }

        } else if (data.type === 'result') { // Final result, mostly for loading state
          setLoading(false)
          setError(null); // Clear error on final result
          ws.close()
        } else if (data.type === 'error') {
          setError(data.message)
          setLoading(false)
        }
      } catch (err) {
        console.error("WS Parse Error"), err
        setError("Failed to parse backend message.")
        setLoading(false)
      }
    }

    ws.onerror = (err) => {
      console.error("WS Error"), err
      setError("Connection failed. Ensure the backend is running.")
      setLoading(false)
    }
  }

  const handleReset = () => {
    setHasStarted(false)
    setQuery('')
    setPlaceData(null)
    setHistoryData(null)
    setCurrentDraft(null)
    setImageUrl(null)
    setJudgeResult(null)
    setError(null)
    setLogs([])
  }

  const fillPrompt = (prompt) => {
    setQuery(prompt)
  }

  // Determine if any results are available to show the results view
  const hasResults = placeData || currentDraft || imageUrl || judgeResult;


  // Initial Landing View
  if (!hasStarted) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-4">
        <div className="max-w-6xl w-full text-center">
          <h1 className="text-6xl md:text-9xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-600 to-purple-600 mb-10 drop-shadow-sm pb-4 tracking-tighter">
            Travel Memory Architect
          </h1>
          <p className="text-3xl text-gray-500 mb-16 font-light tracking-wide">
            Where have you been? Let's write the story.
          </p>

          <form onSubmit={handleSubmit} className="w-full flex flex-col items-center space-y-10">
            <div className="w-full max-w-4xl mx-auto bg-white p-8 rounded-[2rem] shadow-2xl ring-1 ring-gray-100 transition-shadow hover:shadow-indigo-200/50">
              <textarea
                className="w-full h-48 md:h-72 p-6 text-3xl md:text-5xl outline-none text-gray-800 resize-none placeholder-gray-300 font-serif leading-relaxed text-center"
                placeholder="Share your memory here..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            
            <button
              type="submit"
              disabled={!query}
              className="bg-indigo-600 text-white font-bold text-2xl px-16 py-5 rounded-full shadow-lg hover:bg-indigo-700 hover:scale-105 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-3"
            >
              <Plane className="animate-pulse w-8 h-8" /> Let's Go
            </button>
          </form>

          <div className="mt-20">
            <p className="text-center text-gray-400 text-sm uppercase tracking-widest font-bold mb-8">Need Inspiration?</p>
            <div className="flex flex-col gap-4 items-center">
              {SAMPLE_PROMPTS.map((prompt, idx) => (
                <button
                  key={idx}
                  onClick={() => fillPrompt(prompt)}
                  className="text-gray-500 hover:text-indigo-600 cursor-pointer transition-colors duration-200 text-xl font-light hover:underline underline-offset-8 decoration-indigo-200"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Journal/Results View
  return (
    <div className="min-h-screen bg-gray-100 pb-20"> {/* Padding bottom for LogPane */}
      {/* Header / Nav */}
      <div className="bg-white shadow-sm p-4 flex justify-between items-center">
        <button 
          onClick={handleReset}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 font-medium transition"
        >
          <ArrowLeft size={20} /> New Journey
        </button>
        <h2 className="text-2xl font-bold text-gray-800">My Travel Journal</h2>
      </div>

      {/* Hero Map */}
      <div className="w-full h-96 bg-gray-200 shadow-lg">
        {loading && !placeData ? ( // Use placeData here
            <div className="w-full h-full flex items-center justify-center bg-gray-50 text-gray-400 text-xl animate-pulse">
                <MapIcon size={48} className="mr-4" /> Finding location...
            </div>
        ) : placeData ? ( // Use placeData here
             <iframe
                width="100%"
                height="100%"
                style={{ border: 0 }}
                loading="lazy"
                allowFullScreen
                src={getMapUrl(placeData)} // Use placeData here
            ></iframe>
        ) : null}
      </div>

      <div className="max-w-5xl mx-auto p-8 bg-white shadow-lg rounded-lg -mt-16 relative z-10">
        {loading && !hasResults && ( // Use hasResults here
             <div className="flex flex-col items-center justify-center py-20">
                <Loader2 size={64} className="text-gray-400 animate-spin mb-4" />
                <p className="text-2xl text-gray-500 animate-pulse">Writing your story...</p>
             </div>
        )}

        {error && (
            <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-8 text-lg shadow-md" role="alert">
                <p className="font-bold">Oh no!</p>
                <p>{error}</p>
            </div>
        )}

        {hasResults && ( // Use hasResults here
            <div className="mt-8 max-w-2xl mx-auto">
                {/* Journal Entry Text Card */}
                {currentDraft && ( // Render only if currentDraft exists
                  <div className="mb-8 bg-white p-8 shadow-xl border border-gray-200 relative min-h-[400px]">
                      <h3 className="text-3xl font-bold text-gray-800 mb-6 flex items-center gap-2 justify-center">
                          <Sparkles className="text-indigo-500" /> Journal Entry
                      </h3>
                      <div className="text-lg text-gray-800 leading-loose font-serif mb-8">
                          {currentDraft.split('\n').map((line, i) => (
                              <p key={i} className="mb-4">{line}</p>
                          ))}
                      </div>
                      {placeData && ( // Use placeData here
                          <div className="pt-6 border-t-2 border-dotted border-gray-300 text-center">
                               <p className="text-xs text-gray-400 uppercase tracking-widest">Location</p>
                               <p className="font-mono text-sm text-gray-600 mt-1">{placeData.address || "Address unavailable"}</p>
                          </div>
                      )}
                  </div>
                )}

                {/* Generated Image Card */}
                {imageUrl && ( // Render only if imageUrl exists
                  <div className="mb-8 bg-white p-4 shadow-xl border border-gray-200">
                      <h3 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2 justify-center">
                          <Camera className="text-purple-500" /> Visual Memory
                      </h3>
                      <div className="bg-gray-100 w-full aspect-square flex items-center justify-center overflow-hidden border border-gray-200">
                           {imageUrl ? (
                              <img src={imageUrl} alt="Travel Memory" className="w-full h-full object-cover" />
                           ) : (
                              <Camera size={48} className="text-gray-300" />
                           )}
                      </div>
                      <p className="mt-4 text-center text-sm text-gray-500 italic">{getPlaceName(placeData)}</p> {/* Use placeData here */}
                  </div>
                )}

                {/* Fact Check Card (smaller text) */}
                {judgeResult && ( // Render only if judgeResult exists
                    <div className={`p-4 border rounded-lg text-sm ${judgeResult.pass ? 'border-green-400 bg-green-50' : 'border-red-300 bg-red-50'}`}>
                        <div className="flex items-center justify-center gap-2 mb-2">
                            <Stamp size={16} className={judgeResult.pass ? 'text-green-600' : 'text-red-500'} />
                            <h3 className="font-semibold uppercase tracking-wide text-xs text-gray-700">Fact Check Verdict</h3>
                        </div>
                        <p className="text-center text-gray-800 italic text-xs leading-tight">
                            "{judgeResult.reason}"
                        </p>
                        <div className="mt-2 text-center text-sm opacity-60">
                            Score: {judgeResult.score}/10
                        </div>
                    </div>
                )}
            </div>
        )}
      </div>

      {/* Global Log Pane */}
      {(loading || hasResults || logs.length > 0) && (
        <LogPane logs={logs} />
      )}
    </div>
  )
}

export default App
