"use client";

import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import CodeViewer from '../components/CodeViewer';

export default function TriagePage() {
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
  const [receivedFirstMessage, setReceivedFirstMessage] = useState(false);
  const terminalRef = useRef(null);
  const eventSourceRef = useRef(null);
  const inputRef = useRef(null);
  const autoResizeTimerRef = useRef(null);

  // KB approval state
  const [pendingChanges, setPendingChanges] = useState({}); // { filename: { status, diff, oldContent, newContent } }
  const [acceptingFile, setAcceptingFile] = useState(null);
  const [rejectingFile, setRejectingFile] = useState(null);

  // Export state
  const [exporting, setExporting] = useState(false);

  // Strip ANSI escape codes from text
  function stripAnsi(text) {
    // eslint-disable-next-line no-control-regex
    return text.replace(/\x1b\[[0-9;]*m/g, '');
  }

  // Track if content has been modified
  const hasChanges = useMemo(() => 
    selectedFile?.type === 'knowledge' && editedContent !== fileContent,
    [selectedFile?.type, editedContent, fileContent]
  );

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
  const selectedFileName = useMemo(() => 
    selectedFile ? getFileName(selectedFile.path) : null,
    [selectedFile]
  );
  const selectedFilePendingChange = useMemo(() => 
    selectedFileName ? pendingChanges[selectedFileName] : null,
    [selectedFileName, pendingChanges]
  );

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
      await fetch('/api/triage/stop', {
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
      
      // Start the triage session
      const res = await fetch('/api/triage/start', {
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
      const eventSource = new EventSource(`/api/triage/stream?session=${newSessionId}`);
      eventSourceRef.current = eventSource;
      
      eventSource.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'log') {
            setLogs((prev) => [...prev, { type: 'agent', content: msg.line }]);
            // Enable input after receiving first agent message
            setReceivedFirstMessage(true);
            // Check for KB changes after receiving agent messages
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

  // Handle new chat session button click - reset to initial state
  async function handleNewSession() {
    // Stop existing session first
    if (sessionId) {
      await stopSession();
    }
    // Clear logs and reset state
    setLogs([]);
    setPendingChanges({});
    setReceivedFirstMessage(false);
    setUserInput('');
  }

  // Send user input to the running process (or start session if none exists)
  const sendInput = useCallback(async () => {
    // If no session exists, start one
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
      const res = await fetch('/api/triage/input', {
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
  }, [sessionId, userInput, sendingInput, startSession]);

  // Auto-resize textarea based on content (debounced to prevent layout thrashing)
  const autoResizeInput = useCallback(() => {
    clearTimeout(autoResizeTimerRef.current);
    autoResizeTimerRef.current = setTimeout(() => {
      const textarea = inputRef.current;
      if (textarea) {
        textarea.style.height = 'auto';
        const lineHeight = 20; // matches CSS line-height
        const maxHeight = lineHeight * 10; // 10 lines max
        textarea.style.height = Math.min(textarea.scrollHeight, maxHeight) + 'px';
      }
    }, 100);
  }, []);

  // Handle Enter key in input (Shift+Enter for newline, Enter to send)
  const handleInputKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (userInput.trim() || !sessionId) {
        sendInput();
        // Reset textarea height after sending
        if (inputRef.current) {
          inputRef.current.style.height = 'auto';
        }
      }
    }
  }, [userInput, sessionId, sendInput]);

  // Handle input change with auto-resize
  const handleInputChange = useCallback((e) => {
    setUserInput(e.target.value);
    autoResizeInput();
  }, [autoResizeInput]);

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

  // Export knowledge base to a single markdown file
  async function exportKnowledgeBase() {
    setExporting(true);
    try {
      const res = await fetch('/api/kb-export');
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Export failed');
      }
      
      // Get filename from Content-Disposition header
      const contentDisposition = res.headers.get('Content-Disposition');
      let filename = 'knowledge_base.md';
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="(.+)"/);
        if (match) filename = match[1];
      }
      
      // Create blob and trigger download
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert('Failed to export knowledge base: ' + err.message);
    } finally {
      setExporting(false);
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
  const pendingChangeCount = useMemo(() => Object.keys(pendingChanges).length, [pendingChanges]);

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
        {explorerTab === 'knowledge' && (
          <div className="explorer-footer">
            <button
              className="kb-export-btn"
              onClick={exportKnowledgeBase}
              disabled={exporting || knowledgeFiles.length === 0}
              title={knowledgeFiles.length === 0 ? 'No knowledge base files to export' : 'Export knowledge base as markdown'}
            >
              {exporting ? 'Exporting...' : 'Export'}
            </button>
          </div>
        )}
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
                <CodeViewer content={fileContent} filename={selectedFile.path} />
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
          <span className="chat-mode-label">Triage</span>
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
              <div className="chat-terminal-empty">Click Start to begin triage</div>
            ) : (
              logs.map((message, idx) => (
                message.type === 'user' ? (
                  <div key={idx} className="chat-user-message">
                    <div className="chat-user-bubble">
                      {message.content}
                    </div>
                  </div>
                ) : (
                  <div key={idx} className="chat-terminal-line chat-markdown">
                    <ReactMarkdown
                      components={{
                        a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />
                      }}
                    >
                      {stripAnsi(message.content)}
                    </ReactMarkdown>
                  </div>
                )
              ))
            )}
          </div>
        </div>
        <div className="chat-input-area">
          <textarea
            ref={inputRef}
            className="chat-input"
            value={userInput}
            onChange={handleInputChange}
            onKeyDown={handleInputKeyDown}
            placeholder={
              !sessionId 
                ? 'Click Start to begin...'
                : (!receivedFirstMessage ? 'Waiting for agent...' : 'Type your response...')
            }
            disabled={
              !sessionId ||
              startingSession || 
              sendingInput || 
              chatStatus !== 'running' ||
              !receivedFirstMessage
            }
            rows={1}
          />
          <button
            className="chat-send-btn"
            onClick={sendInput}
            disabled={
              startingSession ||
              sendingInput ||
              (sessionId && chatStatus !== 'running') ||
              (sessionId && !receivedFirstMessage) ||
              (sessionId && !userInput.trim())
            }
          >
            {startingSession ? 'Starting...' : sendingInput ? 'Sending...' : (!sessionId ? 'Start' : 'Send')}
          </button>
        </div>
        {/* No mode selector in triage mode - it's always triage */}
      </div>
    </div>
  );
}
