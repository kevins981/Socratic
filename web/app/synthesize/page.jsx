"use client";

import { useEffect, useState, useRef } from 'react';

export default function SynthesizePage() {
  // Explorer state
  const [explorerTab, setExplorerTab] = useState('source'); // 'source' | 'knowledge'
  const [sourceFiles, setSourceFiles] = useState([]);
  const [knowledgeFiles, setKnowledgeFiles] = useState([]);
  const [loadingFiles, setLoadingFiles] = useState(true);

  // Viewer state
  const [selectedFile, setSelectedFile] = useState(null); // { path, type: 'source' | 'knowledge' }
  const [fileContent, setFileContent] = useState('');
  const [editedContent, setEditedContent] = useState('');
  const [loadingContent, setLoadingContent] = useState(false);
  const [saving, setSaving] = useState(false);

  // Agent chat state
  const [sessionId, setSessionId] = useState(null);
  const [logs, setLogs] = useState([]);
  const [chatStatus, setChatStatus] = useState('idle'); // 'idle' | 'running' | 'exited'
  const [startingSession, setStartingSession] = useState(false);
  const [userInput, setUserInput] = useState('');
  const [sendingInput, setSendingInput] = useState(false);
  const terminalRef = useRef(null);
  const eventSourceRef = useRef(null);

  // Strip ANSI escape codes from text
  function stripAnsi(text) {
    // eslint-disable-next-line no-control-regex
    return text.replace(/\x1b\[[0-9;]*m/g, '');
  }

  // Track if content has been modified
  const hasChanges = selectedFile?.type === 'knowledge' && editedContent !== fileContent;

  // Load files on mount
  useEffect(() => {
    loadFiles();
  }, []);

  // Auto-scroll terminal to bottom when logs change
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs]);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  async function loadFiles() {
    setLoadingFiles(true);
    try {
      // Load source files from input_dir
      const projectInfoRes = await fetch('/api/project-info');
      const projectInfo = await projectInfoRes.json();
      
      if (projectInfo.inputDir) {
        const dirFilesRes = await fetch(`/api/dir-files?dir=${encodeURIComponent(projectInfo.inputDir)}`);
        const dirFilesData = await dirFilesRes.json();
        if (Array.isArray(dirFilesData?.files)) {
          setSourceFiles(dirFilesData.files);
        }
      }

      // Load knowledge base files
      const kbRes = await fetch('/api/knowledge-base');
      const kbData = await kbRes.json();
      if (kbData.exists && Array.isArray(kbData.files)) {
        setKnowledgeFiles(kbData.files);
      }
    } catch (err) {
      console.error('Error loading files:', err);
    } finally {
      setLoadingFiles(false);
    }
  }

  // Load file content when a file is selected
  useEffect(() => {
    if (!selectedFile) {
      setFileContent('');
      setEditedContent('');
      return;
    }

    setLoadingContent(true);
    fetch(`/api/file?path=${encodeURIComponent(selectedFile.path)}`)
      .then((r) => r.json())
      .then((data) => {
        const content = data?.content || '';
        setFileContent(content);
        setEditedContent(content);
      })
      .catch(() => {
        setFileContent('[Error loading file]');
        setEditedContent('[Error loading file]');
      })
      .finally(() => setLoadingContent(false));
  }, [selectedFile?.path]);

  function selectFile(path, type) {
    // If there are unsaved changes, confirm before switching
    if (hasChanges) {
      if (!confirm('You have unsaved changes. Discard them?')) {
        return;
      }
    }
    setSelectedFile({ path, type });
  }

  async function saveFile() {
    if (!selectedFile || selectedFile.type !== 'knowledge' || !hasChanges) return;
    
    setSaving(true);
    try {
      const res = await fetch('/api/knowledge-base', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: selectedFile.path, content: editedContent })
      });
      
      if (res.ok) {
        setFileContent(editedContent);
      } else {
        const data = await res.json();
        alert('Failed to save: ' + (data.error || 'Unknown error'));
      }
    } catch (err) {
      alert('Failed to save: ' + err.message);
    } finally {
      setSaving(false);
    }
  }

  function getFileName(path) {
    return path.split('/').pop();
  }

  // Stop the current session
  async function stopSession() {
    if (!sessionId) return;
    
    // Close the event source
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    
    try {
      await fetch('/api/synthesize/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId })
      });
    } catch (err) {
      console.error('Error stopping session:', err);
    }
    
    setSessionId(null);
    setChatStatus('idle');
  }

  // Start a new session
  async function startSession() {
    setStartingSession(true);
    
    // Stop existing session first
    if (sessionId) {
      await stopSession();
    }
    
    // Clear logs for new session
    setLogs([]);
    
    try {
      // Get project info to get inputDir
      const projectInfoRes = await fetch('/api/project-info');
      const projectInfo = await projectInfoRes.json();
      
      if (!projectInfo.inputDir) {
        setLogs([{ type: 'agent', content: '[ERROR] No inputDir found in project configuration' }]);
        setStartingSession(false);
        return;
      }
      
      // Start the session
      const res = await fetch('/api/synthesize/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inputDir: projectInfo.inputDir })
      });
      
      const data = await res.json();
      
      if (!res.ok || !data.sessionId) {
        setLogs([{ type: 'agent', content: `[ERROR] Failed to start session: ${data.error || 'Unknown error'}` }]);
        setStartingSession(false);
        return;
      }
      
      const newSessionId = data.sessionId;
      setSessionId(newSessionId);
      setChatStatus('running');
      
      // Subscribe to SSE stream
      const eventSource = new EventSource(`/api/synthesize/stream?session=${newSessionId}`);
      eventSourceRef.current = eventSource;
      
      eventSource.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'log') {
            setLogs((prev) => [...prev, { type: 'agent', content: msg.line }]);
          } else if (msg.type === 'status') {
            setChatStatus(msg.status);
            if (msg.status === 'exited' || msg.status === 'error') {
              eventSource.close();
              eventSourceRef.current = null;
            }
          }
        } catch (e) {
          // Ignore parse errors (e.g., keep-alive comments)
        }
      };
      
      eventSource.onerror = () => {
        setChatStatus('exited');
        eventSource.close();
        eventSourceRef.current = null;
      };
      
    } catch (err) {
      setLogs([{ type: 'agent', content: `[ERROR] ${err.message}` }]);
      setChatStatus('idle');
    } finally {
      setStartingSession(false);
    }
  }

  // Handle new chat session button click
  function handleNewSession() {
    startSession();
  }

  // Send user input to the running process
  async function sendInput() {
    if (!sessionId || !userInput.trim() || sendingInput) return;
    
    const messageText = userInput;
    setSendingInput(true);
    
    // Add user message to logs immediately
    setLogs((prev) => [...prev, { type: 'user', content: messageText }]);
    
    try {
      const res = await fetch('/api/synthesize/input', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId, text: messageText })
      });
      
      if (res.ok) {
        setUserInput('');
      } else {
        const data = await res.json();
        console.error('Failed to send input:', data.error);
      }
    } catch (err) {
      console.error('Error sending input:', err);
    } finally {
      setSendingInput(false);
    }
  }

  // Handle Enter key in input
  function handleInputKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendInput();
    }
  }

  const currentFiles = explorerTab === 'source' ? sourceFiles : knowledgeFiles;

  return (
    <div className="three-pane-container">
      {/* Left Pane: File Explorer */}
      <div className="explorer-pane">
        <div className="explorer-tabs">
          <button
            className={`explorer-tab ${explorerTab === 'source' ? 'active' : ''}`}
            onClick={() => setExplorerTab('source')}
          >
            Source Docs
          </button>
          <button
            className={`explorer-tab ${explorerTab === 'knowledge' ? 'active' : ''}`}
            onClick={() => setExplorerTab('knowledge')}
          >
            Knowledge Base
          </button>
        </div>
        <div className="explorer-file-list">
          {loadingFiles ? (
            <div className="explorer-empty">Loading...</div>
          ) : currentFiles.length === 0 ? (
            <div className="explorer-empty">
              {explorerTab === 'source' 
                ? 'No source files found' 
                : 'No knowledge base files'}
            </div>
          ) : (
            currentFiles.map((filePath) => (
              <div
                key={filePath}
                className={`explorer-file-item ${selectedFile?.path === filePath ? 'active' : ''}`}
                onClick={() => selectFile(filePath, explorerTab === 'source' ? 'source' : 'knowledge')}
                title={filePath}
              >
                {getFileName(filePath)}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Middle Pane: File Viewer */}
      <div className="viewer-pane">
        {selectedFile ? (
          <>
            <div className="viewer-header">
              <span className="viewer-filename">{getFileName(selectedFile.path)}</span>
              {selectedFile.type === 'knowledge' && (
                <button
                  className="viewer-save-btn"
                  onClick={saveFile}
                  disabled={!hasChanges || saving}
                >
                  {saving ? 'Saving...' : 'Save'}
                </button>
              )}
            </div>
            <div className="viewer-content">
              {loadingContent ? (
                <div className="loading">Loading...</div>
              ) : selectedFile.type === 'source' ? (
                <pre>{fileContent}</pre>
              ) : (
                <textarea
                  className="viewer-textarea"
                  value={editedContent}
                  onChange={(e) => setEditedContent(e.target.value)}
                  spellCheck={false}
                />
              )}
            </div>
          </>
        ) : (
          <div className="viewer-empty">Select a file to view</div>
        )}
      </div>

      {/* Right Pane: Agent Chat */}
      <div className="chat-pane">
        <div className="chat-header">
          <span>Agent</span>
          {sessionId && (
            <button
              className="chat-new-session-btn"
              onClick={handleNewSession}
              disabled={startingSession}
            >
              {startingSession ? 'Starting...' : 'New Chat Session'}
            </button>
          )}
          {sessionId && (
            <span className={`chat-status chat-status-${chatStatus}`}>
              {chatStatus === 'running' ? 'Running' : chatStatus === 'exited' ? 'Stopped' : chatStatus}
            </span>
          )}
        </div>
        <div className="chat-content">
          {!sessionId && chatStatus === 'idle' ? (
            <button
              className="chat-start-btn"
              onClick={handleNewSession}
              disabled={startingSession}
            >
              {startingSession ? 'Starting...' : 'Start new chat session'}
            </button>
          ) : (
            <div className="chat-terminal" ref={terminalRef}>
              {logs.map((message, idx) => (
                message.type === 'user' ? (
                  <div key={idx} className="chat-user-message">
                    <div className="chat-user-bubble">
                      {message.content}
                    </div>
                  </div>
                ) : (
                  <div key={idx} className="chat-terminal-line">{stripAnsi(message.content)}</div>
                )
              ))}
            </div>
          )}
        </div>
        {sessionId && (
          <div className="chat-input-area">
            <input
              type="text"
              className="chat-input"
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder="Type your response..."
              disabled={chatStatus !== 'running' || sendingInput}
            />
            <button
              className="chat-send-btn"
              onClick={sendInput}
              disabled={!userInput.trim() || chatStatus !== 'running' || sendingInput}
            >
              {sendingInput ? 'Sending...' : 'Send'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
