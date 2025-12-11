import React, { useEffect, useRef, useState } from 'react';
import { Terminal, ChevronDown, ChevronUp } from 'lucide-react';

const LogPane = ({ logs = [], isOpen: initialIsOpen = false }) => {
  const [isOpen, setIsOpen] = useState(initialIsOpen);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current && isOpen) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, isOpen]);

  // Auto-open on error? Optional. For now, strict adherence to "collapsed by default".

  return (
    <div className={`fixed bottom-0 left-0 right-0 z-50 bg-gray-900 border-t border-gray-700 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)] transition-all duration-300 flex flex-col ${isOpen ? 'h-64' : 'h-9'}`}>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="flex-none w-full h-9 bg-gray-800 px-4 flex items-center justify-between text-gray-400 hover:text-white hover:bg-gray-750 transition-colors text-xs font-medium cursor-pointer"
      >
        <div className="flex items-center gap-2 font-mono">
          <Terminal size={12} />
          <span>EXECUTION LOGS</span>
          {logs.length > 0 && (
             <span className="ml-2 bg-gray-700 text-gray-300 px-1.5 rounded text-[10px]">{logs.length} Lines</span>
          )}
        </div>
        {isOpen ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
      </button>

      {isOpen && (
        <div 
          ref={scrollRef}
          className="flex-1 p-3 overflow-y-auto font-mono text-[11px] leading-snug text-green-400 bg-black"
        >
          {logs.length === 0 ? (
            <span className="text-gray-600 italic">Ready...</span>
          ) : (
            logs.map((log, idx) => (
              <div key={idx} className="border-b border-gray-900/50 pb-0.5 mb-0.5 break-words">
                <span className="text-gray-600 select-none mr-2 w-6 inline-block text-right">{(idx + 1).toString().padStart(2, '0')}</span>
                <span className="opacity-90">{log}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default LogPane;