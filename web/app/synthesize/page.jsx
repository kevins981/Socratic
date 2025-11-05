"use client";

import { useEffect, useMemo, useRef, useState } from 'react';
import { useSelectedFiles } from '../selected-files-context';

export default function SynthesizePage() {
  const [showPicker, setShowPicker] = useState(false);
  const [currentDir, setCurrentDir] = useState(null);
  const [dirItems, setDirItems] = useState([]);
  const [loadingDir, setLoadingDir] = useState(false);
  const { selectedPaths, setSelectedPaths, activePath, setActivePath } = useSelectedFiles();
  const [fileContents, setFileContents] = useState({}); // path -> content
  const [loadingContent, setLoadingContent] = useState(false);
  const [selectedDir, setSelectedDir] = useState('');
  const [synthesizeSession, setSynthesizeSession] = useState(null); // { id, status }
  const [logLines, setLogLines] = useState([]);
  const [inputText, setInputText] = useState('');
  const eventSourceRef = useRef(null);
  const [activeTab, setActiveTab] = useState('source'); // 'source' | 'agent'

  function ansiToHtml(input) {
    if (!input) return '';
    const escapeHtml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const colorMap = {
      30: '#000000', 31: '#dc2626', 32: '#16a34a', 33: '#ca8a04', 34: '#2563eb', 35: '#7c3aed', 36: '#0891b2', 37: '#e5e7eb',
      90: '#6b7280', 91: '#ef4444', 92: '#22c55e', 93: '#eab308', 94: '#3b82f6', 95: '#a855f7', 96: '#06b6d4', 97: '#ffffff'
    };
    let html = '';
    let i = 0;
    let openSpan = null; // { color, fontWeight }
    const open = (style) => {
      const parts = [];
      if (style.fontWeight === 'bold') parts.push('font-weight:bold');
      if (style.color) parts.push(`color:${style.color}`);
      html += `<span style="${parts.join(';')}">`;
      openSpan = style;
    };
    const close = () => {
      if (openSpan) {
        html += '</span>';
        openSpan = null;
      }
    };
    const len = input.length;
    while (i < len) {
      const ch = input.charCodeAt(i);
      if (ch === 27 /* ESC */ && i + 1 < len && input[i + 1] === '[') {
        // Parse CSI "\x1b[...m"
        let j = i + 2;
        let codeStr = '';
        while (j < len && input[j] !== 'm') {
          codeStr += input[j++];
        }
        if (j < len && input[j] === 'm') {
          // Apply SGR codes
          const codes = codeStr.split(';').filter(Boolean).map((c) => parseInt(c, 10));
          // Reset default when empty
          if (codes.length === 0) codes.push(0);
          // Build new style
          let nextStyle = openSpan ? { ...openSpan } : { color: null, fontWeight: null };
          for (const code of codes) {
            if (code === 0) { // reset
              nextStyle = { color: null, fontWeight: null };
            } else if (code === 1) { // bold
              nextStyle.fontWeight = 'bold';
            } else if (code >= 30 && code <= 37) {
              nextStyle.color = colorMap[code] || nextStyle.color;
            } else if (code >= 90 && code <= 97) {
              nextStyle.color = colorMap[code] || nextStyle.color;
            } else if (code === 39) { // default fg
              nextStyle.color = null;
            } else if (code === 22) { // normal intensity
              nextStyle.fontWeight = null;
            }
            // Background and extended colors skipped for simplicity
          }
          // If style changed, close/open
          const changed = !openSpan || openSpan.color !== nextStyle.color || openSpan.fontWeight !== nextStyle.fontWeight;
          if (changed) {
            close();
            if (nextStyle.color || nextStyle.fontWeight) open(nextStyle);
          }
          i = j + 1;
          continue;
        }
      }
      // Regular char
      if (input[i] === '\n') {
        html += '\n';
      } else if (input[i] === '\r') {
        // skip carriage return
      } else {
        html += escapeHtml(input[i]);
      }
      i++;
    }
    close();
    return html;
  }

  const hasSelection = selectedPaths.length > 0;

  // selection persistence handled by SelectedFilesProvider

  // Load persisted session state on mount
  useEffect(() => {
    const loadState = async () => {
      try {
        // Get current project root
        const dirResponse = await fetch('/api/dir');
        const dirData = await dirResponse.json();
        const currentProjectRoot = dirData.cwd;
        
        // Check if saved data is from the same project
        const savedProjectRoot = localStorage.getItem('socratic:synthesize:projectRoot');
        
        // If project changed, clear all cached data
        if (savedProjectRoot && savedProjectRoot !== currentProjectRoot) {
          console.log('Project changed, clearing cached data');
          localStorage.removeItem('socratic:synthesize:session');
          localStorage.removeItem('socratic:synthesize:logs');
          localStorage.removeItem('socratic:synthesize:selectedDir');
          localStorage.removeItem('socratic:synthesize:projectRoot');
        }
        
        // Store current project root
        localStorage.setItem('socratic:synthesize:projectRoot', currentProjectRoot);
        
        const savedSession = localStorage.getItem('socratic:synthesize:session');
        const savedLogs = localStorage.getItem('socratic:synthesize:logs');
        const savedDir = localStorage.getItem('socratic:synthesize:selectedDir');
        
        if (savedDir) {
          setSelectedDir(savedDir);
        }
        if (savedSession) {
          const session = JSON.parse(savedSession);
          setSynthesizeSession(session);
          
          // Restore logs
          if (savedLogs) {
            setLogLines(JSON.parse(savedLogs));
          }
          
          // If session is still running, reconnect to the stream
          if (session.status === 'running') {
            reconnectToSession(session.id);
          }
        }
      } catch (err) {
        console.log('Error loading saved session state:', err);
      }
    };
    
    loadState();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist selected directory when it changes
  useEffect(() => {
    try {
      if (selectedDir) {
        localStorage.setItem('socratic:synthesize:selectedDir', selectedDir);
      } else {
        localStorage.removeItem('socratic:synthesize:selectedDir');
      }
    } catch (err) {
      console.log('Error saving selected directory:', err);
    }
  }, [selectedDir]);

  // Persist synthesize session when it changes
  useEffect(() => {
    try {
      if (synthesizeSession) {
        localStorage.setItem('socratic:synthesize:session', JSON.stringify(synthesizeSession));
      } else {
        localStorage.removeItem('socratic:synthesize:session');
      }
    } catch (err) {
      console.log('Error saving synthesize session:', err);
    }
  }, [synthesizeSession]);

  // Persist log lines when they change
  useEffect(() => {
    try {
      if (logLines.length > 0) {
        localStorage.setItem('socratic:synthesize:logs', JSON.stringify(logLines));
      } else {
        localStorage.removeItem('socratic:synthesize:logs');
      }
    } catch (err) {
      console.log('Error saving logs:', err);
    }
  }, [logLines]);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, []);

  function openPicker() {
    setShowPicker(true);
    if (!currentDir && !loadingDir) {
      setLoadingDir(true);
      fetch('/api/dir')
        .then((r) => r.json())
        .then((data) => {
          setCurrentDir(data.cwd || '/');
          setDirItems(Array.isArray(data.items) ? data.items : []);
        })
        .catch(() => {
          setCurrentDir('/');
          setDirItems([]);
        })
        .finally(() => setLoadingDir(false));
    }
  }

  function navigateTo(dir) {
    setLoadingDir(true);
    fetch(`/api/dir?dir=${encodeURIComponent(dir)}`)
      .then((r) => r.json())
      .then((data) => {
        setCurrentDir(data.cwd || dir);
        setDirItems(Array.isArray(data.items) ? data.items : []);
      })
      .catch(() => {
        // keep currentDir as-is on error
      })
      .finally(() => setLoadingDir(false));
  }

  function goUp() {
    if (!currentDir) return;
    const trimmed = currentDir.replace(/\/+$/, '');
    if (trimmed === '/') return;
    const idx = trimmed.lastIndexOf('/');
    const parent = idx <= 0 ? '/' : trimmed.slice(0, idx);
    navigateTo(parent);
  }

  function togglePath(path) {
    setSelectedPaths((prev) =>
      prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path]
    );
  }

  async function confirmSelection() {
    try {
      if (!currentDir) {
        setShowPicker(false);
        return;
      }
      const resp = await fetch(`/api/dir-files?dir=${encodeURIComponent(currentDir)}`);
      const data = await resp.json();
      if (Array.isArray(data?.files)) {
        setSelectedPaths(data.files);
        setSelectedDir(currentDir);
        if (!activePath || (data.files.length > 0 && !data.files.includes(activePath))) {
          setActivePath(data.files[0] || null);
        }
      } else {
        setSelectedPaths([]);
        setSelectedDir(currentDir);
      }
    } catch {
      setSelectedPaths([]);
      setSelectedDir(currentDir || '');
    } finally {
      setShowPicker(false);
    }
  }

  function cancelSelection() {
    setShowPicker(false);
  }

  function reconnectToSession(sessionId) {
    try {
      // Close previous stream if any
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      
      const es = new EventSource(`/api/synthesize/stream?session=${encodeURIComponent(sessionId)}`);
      eventSourceRef.current = es;
      es.onmessage = (ev) => {
        try {
          const payload = JSON.parse(ev.data);
          if (payload.type === 'log' && typeof payload.line === 'string') {
            setLogLines((prev) => [...prev, payload.line]);
          } else if (payload.type === 'status') {
            setSynthesizeSession((prev) => (prev ? { ...prev, status: payload.status || prev.status } : prev));
          }
        } catch {}
      };
      es.onerror = () => {
        // ignore; connection issues handled by browser EventSource
      };
    } catch (err) {
      console.log('Error reconnecting to session:', err);
    }
  }

  async function startSynthesize() {
    if (!selectedDir || (synthesizeSession && synthesizeSession.status === 'running')) return;
    try {
      // Close previous stream if any
      try {
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
          eventSourceRef.current = null;
        }
      } catch {}
      setLogLines([]);
      const resp = await fetch('/api/synthesize/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inputDir: selectedDir })
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || 'Failed to start synthesize');
      const sessionId = data.sessionId;
      setSynthesizeSession({ id: sessionId, status: 'running' });
      setActiveTab('agent');
      reconnectToSession(sessionId);
    } catch (err) {
      setLogLines((prev) => [...prev, `[ERR] ${err?.message || 'Failed to start synthesize'}`]);
    }
  }

  async function submitInput() {
    if (!synthesizeSession || synthesizeSession.status !== 'running' || !inputText) return;
    const text = inputText;
    setInputText('');
    // Echo user input to the console immediately
    setLogLines((prev) => [...prev, `› ${text}`]);
    try {
      await fetch('/api/synthesize/input', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId: synthesizeSession.id, text })
      });
    } catch {}
  }

  useEffect(() => {
    if (!activePath) return;
    if (fileContents[activePath]) return;
    setLoadingContent(true);
    fetch(`/api/file?path=${encodeURIComponent(activePath)}`)
      .then((r) => r.json())
      .then((data) => {
        if (data && typeof data.content === 'string') {
          setFileContents((prev) => ({ ...prev, [activePath]: data.content }));
        } else {
          setFileContents((prev) => ({ ...prev, [activePath]: '[Unable to display file]' }));
        }
      })
      .catch(() => {
        setFileContents((prev) => ({ ...prev, [activePath]: '[Error loading file]' }));
      })
      .finally(() => setLoadingContent(false));
  }, [activePath, fileContents]);

  const picker = showPicker ? (
    <div style={styles.modalOverlay}>
      <div style={styles.modal}>
        <div style={styles.modalHeader}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button onClick={goUp} style={styles.buttonSecondary}>Up</button>
            <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#444' }}>{currentDir || ''}</span>
          </div>
        </div>
        <div style={styles.modalBody}>
          {loadingDir ? (
            <div>Loading files…</div>
          ) : !dirItems || dirItems.length === 0 ? (
            <div>Empty directory.</div>
          ) : (
            <div style={styles.fileList}>
              {dirItems.map((item) => (
                item.isDir ? (
                  <div key={item.path} style={styles.dirRow} onClick={() => navigateTo(item.path)}>
                    <span style={styles.dirName}>📁 {item.name}</span>
                  </div>
                ) : (
                  <div key={item.path} style={styles.checkboxRow}>
                    <span style={{ ...styles.checkboxLabel, color: '#666' }}>{item.name}</span>
                  </div>
                )
              ))}
            </div>
          )}
        </div>
        <div style={styles.modalFooter}>
          <button onClick={cancelSelection} style={styles.buttonSecondary}>Cancel</button>
          <button onClick={confirmSelection} style={styles.buttonPrimary}>Use this directory</button>
        </div>
      </div>
    </div>
  ) : null;

  return (
    <div>
      <h1>Synthesize</h1>

      <div style={styles.tabsHeader}>
        <button onClick={() => setActiveTab('source')} style={activeTab === 'source' ? styles.tabActive : styles.tab}>Source files</button>
        <button onClick={() => setActiveTab('agent')} style={activeTab === 'agent' ? styles.tabActive : styles.tab}>Agent</button>
      </div>

      {activeTab === 'source' ? (
        <>
          {selectedDir ? (
            <div style={styles.selectedDirBar}>
              <span style={styles.selectedDirLabel}>Current directory:</span>
              <span style={styles.selectedDirValue}>{selectedDir}</span>
            </div>
          ) : null}
          <div style={styles.synthesizeBar}>
            <button
              style={(!selectedDir || !!(synthesizeSession && synthesizeSession.status === 'running')) ? styles.buttonPrimaryDisabled : styles.buttonPrimary}
              onClick={startSynthesize}
              disabled={!selectedDir || !!(synthesizeSession && synthesizeSession.status === 'running')}
            >
              Synthesize
            </button>
            {synthesizeSession ? (
              <span style={styles.runStatus}>
                {synthesizeSession.status === 'running' ? 'Running…' : synthesizeSession.status === 'exited' ? 'Completed' : synthesizeSession.status}
              </span>
            ) : null}
          </div>

          {!hasSelection ? (
            <div style={styles.emptyPicker} onClick={openPicker}>
              <div>Click to select directory</div>
            </div>
          ) : (
            <div style={styles.paneContainer}>
              <div style={styles.leftPane}>
                <div style={styles.leftHeader}>
                  <span>Selected files</span>
                  <button onClick={openPicker} style={styles.linkButton}>Change</button>
                </div>
                <div style={styles.leftList}>
                  {selectedPaths.map((p) => (
                    <div
                      key={p}
                      onClick={() => setActivePath(p)}
                      style={p === activePath ? styles.listItemActive : styles.listItem}
                      title={p}
                    >
                      {p.split('/').pop()}
                    </div>
                  ))}
                </div>
              </div>
              <div style={styles.rightPane}>
                <div style={styles.rightHeader}>{activePath || 'No file selected'}</div>
                <div style={styles.viewer}>
                  {activePath ? (
                    loadingContent && !fileContents[activePath] ? (
                      <div>Loading…</div>
                    ) : (
                      <pre style={styles.pre}>{fileContents[activePath] || ''}</pre>
                    )
                  ) : null}
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        // Agent tab: console only
        <>
          {synthesizeSession ? (
            <div style={styles.logContainer}>
              <div style={styles.logHeader}>
                <span>{synthesizeSession.status === 'running' ? 'Running…' : synthesizeSession.status === 'exited' ? 'Completed' : synthesizeSession.status}</span>
              </div>
              <div style={styles.logBox}>
                <pre style={styles.pre} dangerouslySetInnerHTML={{ __html: ansiToHtml(logLines.join('\n')) }} />
              </div>
              <div style={styles.inputRow}>
                <input
                  type="text"
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder="Type response for synthesize script…"
                  style={styles.textInput}
                  disabled={synthesizeSession.status !== 'running'}
                  onKeyDown={(e) => { if (e.key === 'Enter') submitInput(); }}
                />
                <button onClick={submitInput} style={styles.buttonSecondary} disabled={!inputText || synthesizeSession.status !== 'running'}>
                  Send
                </button>
              </div>
            </div>
          ) : (
            <div style={styles.emptyState}>
              <div>No synthesize session yet.</div>
              <div style={{ marginTop: 8, fontSize: 14, color: '#888' }}>
                Select a directory in the Source files tab and click Synthesize to see results here.
              </div>
            </div>
          )}
        </>
      )}

      {picker}
    </div>
  );
}

const styles = {
  selectedDirBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8
  },
  selectedDirLabel: {
    color: '#555'
  },
  selectedDirValue: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 12,
    color: '#333'
  },
  synthesizeBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    marginBottom: 16
  },
  runStatus: {
    color: '#666'
  },
  tabsHeader: {
    display: 'flex',
    gap: 8,
    borderBottom: '1px solid #eee',
    marginBottom: 12
  },
  tab: {
    padding: '6px 10px',
    background: '#f3f4f6',
    color: '#111',
    border: '1px solid #e5e7eb',
    borderRadius: 6,
    cursor: 'pointer'
  },
  tabActive: {
    padding: '6px 10px',
    background: '#ffffff',
    color: '#111',
    border: '1px solid #e5e7eb',
    borderRadius: 6,
    cursor: 'pointer'
  },
  emptyPicker: {
    border: '2px dashed #bbb',
    borderRadius: 8,
    padding: 24,
    textAlign: 'center',
    color: '#666',
    cursor: 'pointer'
  },
  paneContainer: {
    display: 'grid',
    gridTemplateColumns: '280px 1fr',
    gap: 16,
    minHeight: 480
  },
  leftPane: {
    border: '1px solid #e2e2e2',
    borderRadius: 8,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column'
  },
  leftHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 12px',
    borderBottom: '1px solid #eee',
    background: '#fafafa'
  },
  leftList: {
    overflow: 'auto'
  },
  listItem: {
    padding: '8px 12px',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis'
  },
  listItemActive: {
    padding: '8px 12px',
    cursor: 'pointer',
    background: '#eef3ff',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis'
  },
  rightPane: {
    border: '1px solid #e2e2e2',
    borderRadius: 8,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column'
  },
  rightHeader: {
    padding: '8px 12px',
    borderBottom: '1px solid #eee',
    background: '#fafafa',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis'
  },
  viewer: {
    height: 520,
    overflow: 'auto',
    padding: 12
  },
  pre: {
    margin: 0,
    whiteSpace: 'pre',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 13
  },
  modalOverlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.4)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000
  },
  modal: {
    background: '#fff',
    borderRadius: 10,
    width: 720,
    maxHeight: '80vh',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    border: '1px solid #e5e5e5'
  },
  modalHeader: {
    padding: '12px 16px',
    borderBottom: '1px solid #eee',
    background: '#fafafa',
    fontWeight: 600
  },
  modalBody: {
    padding: 16,
    overflow: 'hidden'
  },
  fileList: {
    overflow: 'auto',
    maxHeight: '50vh',
    border: '1px solid #eee',
    borderRadius: 6,
    padding: 8
  },
  dirRow: {
    padding: '6px 4px',
    cursor: 'pointer'
  },
  dirName: {
    fontWeight: 600
  },
  checkboxRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '6px 4px'
  },
  checkboxLabel: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: 12
  },
  modalFooter: {
    padding: 12,
    display: 'flex',
    gap: 8,
    justifyContent: 'flex-end',
    borderTop: '1px solid #eee'
  },
  buttonPrimary: {
    padding: '6px 12px',
    background: '#2b5cff',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer'
  },
  buttonPrimaryDisabled: {
    padding: '6px 12px',
    background: '#ccc',
    color: '#888',
    border: 'none',
    borderRadius: 6,
    cursor: 'not-allowed'
  },
  emptyState: {
    border: '2px dashed #bbb',
    borderRadius: 8,
    padding: 48,
    textAlign: 'center',
    color: '#666',
    marginTop: 16
  },
  buttonSecondary: {
    padding: '6px 12px',
    background: '#f3f4f6',
    color: '#111',
    border: '1px solid #e5e7eb',
    borderRadius: 6,
    cursor: 'pointer'
  },
  linkButton: {
    background: 'transparent',
    border: 'none',
    color: '#2b5cff',
    cursor: 'pointer',
    padding: 0
  },
  logContainer: {
    marginTop: 16,
    display: 'flex',
    flexDirection: 'column',
    gap: 8
  },
  logBox: {
    border: '1px solid #e2e2e2',
    borderRadius: 8,
    padding: 12,
    height: 440,
    overflow: 'auto',
    background: '#0b1020',
    color: '#e5e7eb'
  },
  logHeader: {
    padding: '8px 12px',
    border: '1px solid #e2e2e2',
    borderRadius: 8,
    background: '#fafafa',
    color: '#666'
  },
  inputRow: {
    display: 'flex',
    gap: 8
  },
  textInput: {
    flex: 1,
    padding: '6px 10px',
    border: '1px solid #e5e7eb',
    borderRadius: 6
  }
};
