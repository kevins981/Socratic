"use client";

import { useEffect, useState, useRef } from 'react';

export default function SynthesizePage() {
  // Explorer state
  const [explorerTab, setExplorerTab] = useState('source'); // 'source' | 'knowledge'
  const [sourceTree, setSourceTree] = useState(null);
  const [knowledgeFiles, setKnowledgeFiles] = useState([]);
  const [loadingFiles, setLoadingFiles] = useState(true);
  const [expandedFolders, setExpandedFolders] = useState({});

  // Viewer state
  const [selectedFile, setSelectedFile] = useState(null); // { path, type: 'source' | 'knowledge' }
  const [fileRefreshKey, setFileRefreshKey] = useState(0); // Increment to force re-fetch file content
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
  const [agentMode, setAgentMode] = useState('synth'); // 'synth' | 'digest'
  const [modeDropdownOpen, setModeDropdownOpen] = useState(false);
  const [receivedFirstMessage, setReceivedFirstMessage] = useState(false); // For digest mode
  const terminalRef = useRef(null);
  const eventSourceRef = useRef(null);

  // KB approval state
  const [pendingChanges, setPendingChanges] = useState({}); // { filename: { status, diff, oldContent, newContent } }
  const [acceptingFile, setAcceptingFile] = useState(null);
  const [rejectingFile, setRejectingFile] = useState(null);

  // Strip ANSI escape codes from text
  function stripAnsi(text) {
    // eslint-disable-next-line no-control-regex
    return text.replace(/\x1b\[[0-9;]*m/g, '');
  }

  // Track if content has been modified
  const hasChanges = selectedFile?.type === 'knowledge' && editedContent !== fileContent;

  // Get the filename from a path
  function getFileName(path) {
    return path.split('/').pop();
  }

  // Convert a list of file paths into a folder tree
  function buildTree(paths, baseDir) {
    if (!Array.isArray(paths) || paths.length === 0) {
      return null;
    }

    const rootPath = baseDir || '';
    const rootName = rootPath ? getFileName(rootPath) : 'Source';
    const root = { name: rootName, path: rootPath, type: 'folder', children: [] };
    const dirMap = new Map();
    dirMap.set(rootPath || '__root__', root);

    function toRelative(absPath) {
      if (rootPath && absPath.startsWith(rootPath)) {
        const trimmed = absPath.slice(rootPath.length);
        return trimmed.startsWith('/') ? trimmed.slice(1) : trimmed;
      }
      return absPath;
    }

    function ensureDir(parts, idx, parentNode) {
      const dirParts = parts.slice(0, idx + 1);
      const key = (rootPath ? `${rootPath}/` : '') + dirParts.join('/');
      if (!dirMap.has(key)) {
        const dirNode = {
          name: parts[idx],
          path: key,
          type: 'folder',
          children: [],
        };
        dirMap.set(key, dirNode);
        parentNode.children.push(dirNode);
        return dirNode;
      }
      return dirMap.get(key);
    }

    for (const absPath of paths) {
      const relPath = toRelative(absPath);
      const parts = relPath.split('/').filter(Boolean);
      if (parts.length === 0) continue;

      let parent = root;
      parts.forEach((part, idx) => {
        const isLast = idx === parts.length - 1;
        if (isLast) {
          parent.children.push({ name: part, path: absPath, type: 'file' });
        } else {
          parent = ensureDir(parts, idx, parent);
        }
      });
    }

    function sortNode(node) {
      if (!node.children) return;
      node.children.sort((a, b) => {
        if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      node.children.forEach(sortNode);
    }
    sortNode(root);
    return root;
  }

  // Check if selected file has pending changes
  const selectedFileName = selectedFile ? getFileName(selectedFile.path) : null;
  const selectedFilePendingChange = selectedFileName ? pendingChanges[selectedFileName] : null;

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

  // Fetch KB diffs
  async function fetchKbDiff() {
    try {
      const res = await fetch('/api/kb-diff');
      const data = await res.json();
      
      if (data.changedFiles && Array.isArray(data.changedFiles)) {
        const changesMap = {};
        for (const change of data.changedFiles) {
          changesMap[change.filename] = change;
        }
        setPendingChanges(changesMap);
      }
    } catch (err) {
      console.error('Error fetching KB diff:', err);
    }
  }

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
          const tree = buildTree(dirFilesData.files, projectInfo.inputDir);
          setSourceTree(tree);
          if (tree) {
            setExpandedFolders((prev) => {
              const key = tree.path || '__root__';
              if (prev[key]) return prev;
              return { ...prev, [key]: true };
            });
          }
        }
      }

      // Load knowledge base files
      const kbRes = await fetch('/api/knowledge-base');
      const kbData = await kbRes.json();
      if (kbData.exists && Array.isArray(kbData.files)) {
        setKnowledgeFiles(kbData.files);
      }

      // Also fetch KB diffs
      await fetchKbDiff();
    } catch (err) {
      console.error('Error loading files:', err);
    } finally {
      setLoadingFiles(false);
    }
  }

  // Load file content when a file is selected or refreshKey changes
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
  }, [selectedFile?.path, fileRefreshKey]);

  function selectFile(path, type) {
    // If there are unsaved changes, confirm before switching
    if (hasChanges) {
      if (!confirm('You have unsaved changes. Discard them?')) {
        return;
      }
    }
    setSelectedFile({ path, type });
    setFileRefreshKey((k) => k + 1); // Force re-fetch file content
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
    
    // Clear logs and pending changes for new session
    setLogs([]);
    setPendingChanges({});
    setReceivedFirstMessage(false);
    
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
        body: JSON.stringify({ inputDir: projectInfo.inputDir, mode: agentMode })
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
            // For digest mode, enable input after receiving first agent message
            setReceivedFirstMessage(true);
            // Check for KB changes after receiving agent messages
            // We debounce this by checking on non-empty lines that aren't status messages
            const line = msg.line.trim();
            if (line && !line.startsWith('[') && !line.includes('in progress')) {
              fetchKbDiff();
            }
          } else if (msg.type === 'status') {
            setChatStatus(msg.status);
            // Fetch diffs when agent finishes a response
            if (msg.status === 'waiting' || msg.status === 'exited') {
              fetchKbDiff();
            }
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

  // Handle new chat session button click - reset to initial state for mode selection
  async function handleNewSession() {
    // Stop existing session first
    if (sessionId) {
      await stopSession();
    }
    // Clear logs and reset state to allow mode selection
    setLogs([]);
    setPendingChanges({});
    setReceivedFirstMessage(false);
    setUserInput('');
    // sessionId and chatStatus are already reset by stopSession()
  }

  // Send user input to the running process (or start session if none exists)
  async function sendInput() {
    // If no session exists, start one (input is disabled, so this is just clicking Start)
    if (!sessionId) {
      await startSession();
      return;
    }
    
    if (!userInput.trim() || sendingInput) return;
    
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
      if (userInput.trim() || !sessionId) {
        sendInput();
      }
    }
  }

  // Accept changes for a file
  async function acceptFile(filename) {
    setAcceptingFile(filename);
    try {
      const res = await fetch('/api/kb-accept-file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename })
      });
      
      if (res.ok) {
        // Remove from pending changes
        setPendingChanges((prev) => {
          const next = { ...prev };
          delete next[filename];
          return next;
        });
        // Refresh files list and content
        await loadFiles();
        // If we're viewing this file, reload its content
        if (selectedFileName === filename) {
          const change = pendingChanges[filename];
          if (change) {
            setFileContent(change.newContent);
            setEditedContent(change.newContent);
          }
        }
      } else {
        const data = await res.json();
        alert('Failed to accept: ' + (data.error || 'Unknown error'));
      }
    } catch (err) {
      alert('Failed to accept: ' + err.message);
    } finally {
      setAcceptingFile(null);
    }
  }

  // Reject changes for a file
  async function rejectFile(filename) {
    setRejectingFile(filename);
    try {
      const res = await fetch('/api/kb-reject-file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename })
      });
      
      if (res.ok) {
        // Remove from pending changes
        setPendingChanges((prev) => {
          const next = { ...prev };
          delete next[filename];
          return next;
        });
        // Refresh KB diff to ensure state is consistent
        await fetchKbDiff();
      } else {
        const data = await res.json();
        alert('Failed to reject: ' + (data.error || 'Unknown error'));
      }
    } catch (err) {
      alert('Failed to reject: ' + err.message);
    } finally {
      setRejectingFile(null);
    }
  }

  // Render diff view
  function renderDiffView(change) {
    if (!change || !change.diff) return null;

    return (
      <div className="diff-view">
        <div className="diff-header">
          <span className={`diff-status diff-status-${change.status}`}>
            {change.status === 'added' ? 'New File' : 
             change.status === 'deleted' ? 'Deleted' : 'Modified'}
          </span>
        </div>
        <div className="diff-content">
          {change.diff.map((line, idx) => (
            <div 
              key={idx} 
              className={`diff-line diff-line-${line.type}`}
            >
              <span className="diff-line-prefix">
                {line.type === 'add' ? '+' : line.type === 'del' ? '-' : ' '}
              </span>
              <span className="diff-line-content">{line.line}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  function toggleFolder(pathKey) {
    setExpandedFolders((prev) => ({
      ...prev,
      [pathKey]: !prev[pathKey],
    }));
  }

  function renderTree(node, depth = 0) {
    if (!node) return null;
    const isFolder = node.type === 'folder';
    const pathKey = node.path || '__root__';
    const isExpanded = expandedFolders[pathKey] ?? false;
    const paddingLeft = 12 + depth * 12;

    if (isFolder) {
      return (
        <div key={pathKey}>
          <div
            className="explorer-file-item explorer-folder"
            style={{ paddingLeft }}
            onClick={() => toggleFolder(pathKey)}
            title={node.path || 'Source'}
          >
            <span className={`folder-caret ${isExpanded ? 'open' : ''}`}>▸</span>
            <span className="folder-label">{node.name || 'Source'}</span>
          </div>
          {isExpanded &&
            node.children?.map((child) => renderTree(child, depth + 1))}
        </div>
      );
    }

    return (
      <div
        key={node.path}
        className={`explorer-file-item explorer-file ${selectedFile?.path === node.path ? 'active' : ''}`}
        style={{ paddingLeft }}
        onClick={() => selectFile(node.path, 'source')}
        title={node.path}
      >
        {node.name}
      </div>
    );
  }
  const pendingChangeCount = Object.keys(pendingChanges).length;

  return (
    <div className="three-pane-container">
      {/* Left Pane: File Explorer */}
      <div className="explorer-pane">
        <div className="explorer-tabs">
          <button
            className={`explorer-tab ${explorerTab === 'source' ? 'active' : ''}`}
            onClick={() => {
              setExplorerTab('source');
              loadFiles();
            }}
          >
            Source Docs
          </button>
          <button
            className={`explorer-tab ${explorerTab === 'knowledge' ? 'active' : ''}`}
            onClick={() => {
              setExplorerTab('knowledge');
              loadFiles();
            }}
          >
            Knowledge Base
            {pendingChangeCount > 0 && (
              <span className="pending-badge">{pendingChangeCount}</span>
            )}
          </button>
        </div>
        <div className="explorer-file-list">
          {loadingFiles ? (
            <div className="explorer-empty">Loading...</div>
        ) : explorerTab === 'source' ? (
          !sourceTree || !sourceTree.children?.length ? (
            <div className="explorer-empty">No source files found</div>
          ) : (
            renderTree(sourceTree)
          )
        ) : knowledgeFiles.length === 0 ? (
          <div className="explorer-empty">No knowledge base files</div>
        ) : (
          knowledgeFiles.map((filePath) => {
            const fileName = getFileName(filePath);
            const hasPending = pendingChanges[fileName];
            return (
              <div
                key={filePath}
                className={`explorer-file-item ${selectedFile?.path === filePath ? 'active' : ''} ${hasPending ? 'has-pending-change' : ''}`}
                onClick={() => selectFile(filePath, 'knowledge')}
                title={filePath}
              >
                {hasPending && <span className="file-change-indicator"></span>}
                {fileName}
              </div>
            );
          })
        )}
          {/* Show added files that aren't in the KB list yet */}
          {explorerTab === 'knowledge' && Object.entries(pendingChanges)
            .filter(([filename, change]) => change.status === 'added')
            .filter(([filename]) => !knowledgeFiles.some(f => getFileName(f) === filename))
            .map(([filename, change]) => (
              <div
                key={`pending-${filename}`}
                className={`explorer-file-item has-pending-change ${selectedFileName === filename ? 'active' : ''}`}
                onClick={() => selectFile(change.userPath, 'knowledge')}
                title={`${filename} (pending)`}
              >
                <span className="file-change-indicator file-change-added"></span>
                {filename}
              </div>
            ))
          }
        </div>
      </div>

      {/* Middle Pane: File Viewer */}
      <div className="viewer-pane">
        {selectedFile ? (
          <>
            <div className="viewer-header">
              <span className="viewer-filename">{getFileName(selectedFile.path)}</span>
              <div className="viewer-actions">
                {selectedFilePendingChange && (
                  <>
                    <button
                      className="viewer-accept-btn"
                      onClick={() => acceptFile(selectedFileName)}
                      disabled={acceptingFile === selectedFileName}
                    >
                      {acceptingFile === selectedFileName ? 'Accepting...' : 'Accept'}
                    </button>
                    <button
                      className="viewer-reject-btn"
                      onClick={() => rejectFile(selectedFileName)}
                      disabled={rejectingFile === selectedFileName}
                    >
                      {rejectingFile === selectedFileName ? 'Rejecting...' : 'Reject'}
                    </button>
                  </>
                )}
                {selectedFile.type === 'knowledge' && !selectedFilePendingChange && (
                  <button
                    className="viewer-save-btn"
                    onClick={saveFile}
                    disabled={!hasChanges || saving}
                  >
                    {saving ? 'Saving...' : 'Save'}
                  </button>
                )}
              </div>
            </div>
            <div className="viewer-content">
              {loadingContent ? (
                <div className="loading">Loading...</div>
              ) : selectedFilePendingChange ? (
                renderDiffView(selectedFilePendingChange)
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
          <span className="chat-mode-label">{sessionId ? (agentMode === 'synth' ? 'Synth' : 'Digest') : 'Agent'}</span>
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
          <div className="chat-terminal" ref={terminalRef}>
            {logs.length === 0 && !sessionId ? (
              <div className="chat-terminal-empty">Select a mode and click Start to begin</div>
            ) : (
              logs.map((message, idx) => (
                message.type === 'user' ? (
                  <div key={idx} className="chat-user-message">
                    <div className="chat-user-bubble">
                      {message.content}
                    </div>
                  </div>
                ) : (
                  <div key={idx} className="chat-terminal-line">{stripAnsi(message.content)}</div>
                )
              ))
            )}
          </div>
        </div>
        <div className="chat-input-area">
          <input
            type="text"
            className="chat-input"
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            onKeyDown={handleInputKeyDown}
            placeholder={
              !sessionId 
                ? 'Click Start to begin...'
                : (agentMode === 'digest' && !receivedFirstMessage ? 'Waiting for agent...' : 'Type your response...')
            }
            disabled={
              !sessionId ||
              startingSession || 
              sendingInput || 
              chatStatus !== 'running' ||
              (agentMode === 'digest' && !receivedFirstMessage)
            }
          />
          <button
            className="chat-send-btn"
            onClick={sendInput}
            disabled={
              startingSession ||
              sendingInput ||
              (sessionId && chatStatus !== 'running') ||
              (sessionId && agentMode === 'digest' && !receivedFirstMessage) ||
              (sessionId && !userInput.trim())
            }
          >
            {startingSession ? 'Starting...' : sendingInput ? 'Sending...' : (!sessionId ? 'Start' : 'Send')}
          </button>
        </div>
        {/* Mode selector - only show when no session is running */}
        {!sessionId && (
          <div className="chat-mode-selector">
            <div className="mode-dropdown-container">
              <button
                className="mode-dropdown-trigger"
                onClick={() => setModeDropdownOpen(!modeDropdownOpen)}
              >
                <span className="mode-dropdown-label">Mode:</span>
                <span className="mode-dropdown-value">{agentMode === 'synth' ? 'Synth' : 'Digest'}</span>
                <span className={`mode-dropdown-arrow ${modeDropdownOpen ? 'open' : ''}`}>▾</span>
              </button>
              {modeDropdownOpen && (
                <div className="mode-dropdown-menu">
                  <button
                    className={`mode-dropdown-item ${agentMode === 'synth' ? 'active' : ''}`}
                    onClick={() => { setAgentMode('synth'); setModeDropdownOpen(false); }}
                  >
                    <span className="mode-item-name">Synth</span>
                    <span className="mode-item-desc">User-directed updates</span>
                  </button>
                  <button
                    className={`mode-dropdown-item ${agentMode === 'digest' ? 'active' : ''}`}
                    onClick={() => { setAgentMode('digest'); setModeDropdownOpen(false); }}
                  >
                    <span className="mode-item-name">Digest</span>
                    <span className="mode-item-desc">Question-first learning</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
