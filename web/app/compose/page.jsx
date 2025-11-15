"use client";

import { useEffect, useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';

export default function ComposePage() {
  const [activeTab, setActiveTab] = useState('compose');
  const [allUnits, setAllUnits] = useState([]); // [{ unit: {...}, conceptFile: "..." }]
  const [selectedUnits, setSelectedUnits] = useState(new Set());
  const [expandedUnits, setExpandedUnits] = useState(new Set());
  const [hoveredUnit, setHoveredUnit] = useState(null);
  const [loadingUnits, setLoadingUnits] = useState(false);
  const [composeSession, setComposeSession] = useState(null); // { id, status }
  const [logLines, setLogLines] = useState([]);
  const [outputContent, setOutputContent] = useState('');
  const [outputFilename, setOutputFilename] = useState('');
  const [loadingOutput, setLoadingOutput] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);
  const [kbData, setKbData] = useState(null); // { name1: "prompt1", name2: "prompt2", ... }
  const [selectedPromptName, setSelectedPromptName] = useState(null);
  const [loadingKB, setLoadingKB] = useState(false);
  const [kbKeysBeforeCompose, setKbKeysBeforeCompose] = useState(null); // Track KB keys before compose starts
  const eventSourceRef = useRef(null);

  // Load persisted state on mount
  useEffect(() => {
    const loadState = async () => {
      try {
        // Get current project root
        const dirResponse = await fetch('/api/dir');
        const dirData = await dirResponse.json();
        const currentProjectRoot = dirData.cwd;
        
        // Check if saved data is from the same project
        const savedProjectRoot = localStorage.getItem('socratic:compose:projectRoot');
        
        // If project changed, clear all cached data
        if (savedProjectRoot && savedProjectRoot !== currentProjectRoot) {
          console.log('Project changed, clearing cached data');
          localStorage.removeItem('socratic:compose:session');
          localStorage.removeItem('socratic:compose:logs');
          localStorage.removeItem('socratic:compose:projectRoot');
        }
        
        // Store current project root
        localStorage.setItem('socratic:compose:projectRoot', currentProjectRoot);
        
        const savedSession = localStorage.getItem('socratic:compose:session');
        const savedLogs = localStorage.getItem('socratic:compose:logs');
        
        if (savedSession) {
          const session = JSON.parse(savedSession);
          
          // Only restore completed sessions, clear stale 'running' sessions
          if (session.status === 'running') {
            // Clear stale running session from previous page load
            localStorage.removeItem('socratic:compose:session');
            localStorage.removeItem('socratic:compose:logs');
          } else {
            setComposeSession(session);
            
            // Restore logs
            if (savedLogs) {
              setLogLines(JSON.parse(savedLogs));
            }
          }
        }
      } catch (err) {
        console.log('Error loading saved state:', err);
      }
    };
    
    loadState();
    loadKnowledgeUnits();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist compose session when it changes
  useEffect(() => {
    try {
      if (composeSession) {
        localStorage.setItem('socratic:compose:session', JSON.stringify(composeSession));
      } else {
        localStorage.removeItem('socratic:compose:session');
      }
    } catch (err) {
      console.log('Error saving compose session:', err);
    }
  }, [composeSession]);

  // Persist log lines when they change
  useEffect(() => {
    try {
      if (logLines.length > 0) {
        localStorage.setItem('socratic:compose:logs', JSON.stringify(logLines));
      } else {
        localStorage.removeItem('socratic:compose:logs');
      }
    } catch (err) {
      console.log('Error saving logs:', err);
    }
  }, [logLines]);

  // Load output content and switch to Output tab when session completes
  useEffect(() => {
    if (composeSession && composeSession.status === 'exited') {
      loadOutputFile();
      // Switch to Output tab when compose completes
      setActiveTab('output');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [composeSession?.status]);

  // Load KB data whenever user clicks on Output tab
  useEffect(() => {
    if (activeTab === 'output') {
      // Check if we just completed a compose session and should select new item
      const shouldSelectNew = composeSession && composeSession.status === 'exited' && kbKeysBeforeCompose;
      loadKBData(shouldSelectNew);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, []);

  function ansiToHtml(input) {
    if (!input) return '';
    const escapeHtml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const colorMap = {
      30: '#000000', 31: '#dc2626', 32: '#16a34a', 33: '#ca8a04', 34: '#2563eb', 35: '#7c3aed', 36: '#0891b2', 37: '#e5e7eb',
      90: '#6b7280', 91: '#ef4444', 92: '#22c55e', 93: '#eab308', 94: '#3b82f6', 95: '#a855f7', 96: '#06b6d4', 97: '#ffffff'
    };
    let html = '';
    let i = 0;
    let openSpan = null;
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
      if (ch === 27 && i + 1 < len && input[i + 1] === '[') {
        let j = i + 2;
        let codeStr = '';
        while (j < len && input[j] !== 'm') {
          codeStr += input[j++];
        }
        if (j < len && input[j] === 'm') {
          const codes = codeStr.split(';').filter(Boolean).map((c) => parseInt(c, 10));
          if (codes.length === 0) codes.push(0);
          let nextStyle = openSpan ? { ...openSpan } : { color: null, fontWeight: null };
          for (const code of codes) {
            if (code === 0) {
              nextStyle = { color: null, fontWeight: null };
            } else if (code === 1) {
              nextStyle.fontWeight = 'bold';
            } else if (code >= 30 && code <= 37) {
              nextStyle.color = colorMap[code] || nextStyle.color;
            } else if (code >= 90 && code <= 97) {
              nextStyle.color = colorMap[code] || nextStyle.color;
            } else if (code === 39) {
              nextStyle.color = null;
            } else if (code === 22) {
              nextStyle.fontWeight = null;
            }
          }
          const changed = !openSpan || openSpan.color !== nextStyle.color || openSpan.fontWeight !== nextStyle.fontWeight;
          if (changed) {
            close();
            if (nextStyle.color || nextStyle.fontWeight) open(nextStyle);
          }
          i = j + 1;
          continue;
        }
      }
      if (input[i] === '\n') {
        html += '\n';
      } else if (input[i] === '\r') {
        // skip
      } else {
        html += escapeHtml(input[i]);
      }
      i++;
    }
    close();
    return html;
  }

  async function loadKnowledgeUnits() {
    setLoadingUnits(true);
    try {
      const response = await fetch('/api/compose/list');
      if (response.ok) {
        const data = await response.json();
        setAllUnits(data.units || []);
      } else {
        console.error('Failed to load knowledge units');
      }
    } catch (err) {
      console.error('Error loading knowledge units:', err);
    } finally {
      setLoadingUnits(false);
    }
  }

  async function loadOutputFile() {
    setLoadingOutput(true);
    try {
      const response = await fetch('/api/compose/output');
      if (response.ok) {
        const data = await response.json();
        setOutputContent(data.content || '');
        setOutputFilename(data.filename || '');
      } else {
        const data = await response.json();
        if (data.notYetRun) {
          setOutputContent('NOT_YET_RUN');
        } else {
          setOutputContent('Error: Failed to load output file');
        }
        setOutputFilename('');
      }
    } catch (err) {
      setOutputContent('Error: ' + (err?.message || 'Failed to load output'));
      setOutputFilename('');
    } finally {
      setLoadingOutput(false);
    }
  }

  async function loadKBData(selectNewItem = false) {
    setLoadingKB(true);
    try {
      const response = await fetch('/api/compose/kb');
      if (response.ok) {
        const data = await response.json();
        setKbData(data.kbData || null);
        // Select the appropriate prompt
        if (data.kbData) {
          const keys = Object.keys(data.kbData);
          if (keys.length > 0) {
            if (selectNewItem && kbKeysBeforeCompose) {
              // Find the new key(s) that weren't in the previous KB
              const newKeys = keys.filter(k => !kbKeysBeforeCompose.includes(k));
              if (newKeys.length > 0) {
                // Select the first new key
                setSelectedPromptName(newKeys[0]);
              } else {
                // No new keys, select the first one
                setSelectedPromptName(keys[0]);
              }
              // Clear the tracking
              setKbKeysBeforeCompose(null);
            } else {
              // Default: select the first prompt
              setSelectedPromptName(keys[0]);
            }
          }
        }
      } else {
        setKbData(null);
      }
    } catch (err) {
      console.error('Error loading KB data:', err);
      setKbData(null);
    } finally {
      setLoadingKB(false);
    }
  }

  async function copyToClipboard() {
    try {
      await navigator.clipboard.writeText(outputContent);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  }

  function toggleUnit(index) {
    setSelectedUnits((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }

  function toggleExpand(index) {
    setExpandedUnits((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }

  function getUnitDisplayName(unit) {
    const heading = unit.heading || 'unnamed';
    return heading;
  }

  function renderValue(value) {
    if (value === null) return <span style={styles.jsonValue}>null</span>;
    if (value === undefined) return <span style={styles.jsonValue}>undefined</span>;
    if (typeof value === 'boolean') return <span style={styles.jsonValue}>{value.toString()}</span>;
    if (typeof value === 'number') return <span style={styles.jsonValue}>{value}</span>;
    if (typeof value === 'string') {
      // Split by newlines and render each line
      const lines = value.split('\n');
      return (
        <div style={styles.jsonValue}>
          {lines.map((line, idx) => (
            <div key={idx} style={{ marginBottom: idx < lines.length - 1 ? '4px' : '0' }}>
              {line || '\u00A0'}
            </div>
          ))}
        </div>
      );
    }
    return <span style={styles.jsonValue}>{JSON.stringify(value)}</span>;
  }

  function renderJsonContent(obj, depth = 0) {
    if (!obj || typeof obj !== 'object') {
      return renderValue(obj);
    }

    const indent = depth * 20;
    
    if (Array.isArray(obj)) {
      if (obj.length === 0) {
        return <span style={styles.jsonValue}>[]</span>;
      }
      return (
        <div style={{ marginLeft: `${indent}px` }}>
          {obj.map((item, idx) => (
            <div key={idx} style={styles.jsonField}>
              <div style={styles.jsonKey}>[{idx}]</div>
              <div style={styles.jsonValueContainer}>
                {typeof item === 'object' && item !== null ? (
                  renderJsonContent(item, depth + 1)
                ) : (
                  renderValue(item)
                )}
              </div>
            </div>
          ))}
        </div>
      );
    }

    const entries = Object.entries(obj);
    if (entries.length === 0) {
      return <span style={styles.jsonValue}>{'{}'}</span>;
    }

    return (
      <div style={{ marginLeft: `${indent}px` }}>
        {entries.map(([key, value]) => (
          <div key={key} style={styles.jsonField}>
            <div style={styles.jsonKey}>{key}</div>
            <div style={styles.jsonValueContainer}>
              {typeof value === 'object' && value !== null ? (
                renderJsonContent(value, depth + 1)
              ) : (
                renderValue(value)
              )}
            </div>
          </div>
        ))}
      </div>
    );
  }

  function reconnectToSession(sessionId) {
    try {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      
      const es = new EventSource(`/api/compose/stream?session=${encodeURIComponent(sessionId)}`);
      eventSourceRef.current = es;
      es.onmessage = (ev) => {
        try {
          const payload = JSON.parse(ev.data);
          if (payload.type === 'log' && typeof payload.line === 'string') {
            setLogLines((prev) => [...prev, payload.line]);
          } else if (payload.type === 'status') {
            setComposeSession((prev) => (prev ? { ...prev, status: payload.status || prev.status } : prev));
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

  async function startCompose() {
    if (selectedUnits.size === 0 || (composeSession && composeSession.status === 'running')) return;
    
    // Get the actual unit objects (not the indices)
    const unitsToCompose = Array.from(selectedUnits).map(idx => allUnits[idx].unit);
    
    try {
      // Save current KB keys before starting compose
      if (kbData) {
        setKbKeysBeforeCompose(Object.keys(kbData));
      }
      
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      setLogLines([]);
      setOutputContent('');
      const resp = await fetch('/api/compose/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selectedUnits: unitsToCompose })
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || 'Failed to start compose');
      const sessionId = data.sessionId;
      setComposeSession({ id: sessionId, status: 'running' });
      // Stay on Compose tab while running - will auto-switch when complete
      reconnectToSession(sessionId);
    } catch (err) {
      setLogLines((prev) => [...prev, `[ERR] ${err?.message || 'Failed to start compose'}`]);
    }
  }

  const isRunning = composeSession && composeSession.status === 'running';
  const canCompose = selectedUnits.size > 0 && !isRunning;

  return (
    <div>
      <div style={styles.tabsHeader}>
        <button onClick={() => setActiveTab('compose')} style={activeTab === 'compose' ? styles.tabActive : styles.tab}>Compose</button>
        <button onClick={() => setActiveTab('output')} style={activeTab === 'output' ? styles.tabActive : styles.tab}>Output</button>
      </div>

      {activeTab === 'compose' ? (
        <>
          <div style={styles.composeBar}>
            <button
              style={canCompose ? styles.composeButton : styles.composeButtonDisabled}
              onClick={startCompose}
              disabled={!canCompose}
            >
              Compose
            </button>
            {composeSession ? (
              <span style={styles.runStatus}>
                {composeSession.status === 'running' ? 'Running…' : composeSession.status === 'exited' ? 'Completed' : composeSession.status}
              </span>
            ) : null}
          </div>

          {loadingUnits && (
            <div style={styles.loading}>Loading knowledge units...</div>
          )}

          {!loadingUnits && allUnits.length === 0 && (
            <div style={styles.emptyMessage}>
              No knowledge units found. Please run synthesize first to generate concept files.
            </div>
          )}

          {!loadingUnits && allUnits.length > 0 && (
            <div style={styles.contentArea}>
              <h2 style={styles.contentTitle}>
                Select Knowledge Units ({selectedUnits.size} selected):
              </h2>
              <div style={styles.unitsList}>
                {allUnits.map((item, index) => {
                  const isExpanded = expandedUnits.has(index);
                  return (
                    <div key={index} style={styles.unitContainer}>
                      <div style={styles.unitItem}>
                        <input
                          type="checkbox"
                          checked={selectedUnits.has(index)}
                          onChange={(e) => {
                            e.stopPropagation();
                            toggleUnit(index);
                          }}
                          onClick={(e) => e.stopPropagation()}
                          disabled={isRunning}
                          style={styles.checkbox}
                        />
                        <div
                          style={{
                            ...styles.unitLabelArea,
                            backgroundColor: hoveredUnit === index ? '#f3f4f6' : 'transparent',
                          }}
                          onClick={() => toggleExpand(index)}
                          onMouseEnter={() => setHoveredUnit(index)}
                          onMouseLeave={() => setHoveredUnit(null)}
                        >
                          <span style={styles.chevronIcon}>
                            {isExpanded ? '▼' : '▶'}
                          </span>
                          <span style={styles.unitLabel}>
                            {getUnitDisplayName(item.unit)}
                          </span>
                        </div>
                      </div>
                      {isExpanded && (
                        <div style={styles.expandedContent}>
                          <div style={styles.bodyText}>
                            <ReactMarkdown>{(item.unit.body || 'No content').trim()}</ReactMarkdown>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      ) : (
        // Output tab: KB viewer
        <>
          {loadingKB ? (
            <div style={styles.loading}>Loading knowledge base...</div>
          ) : kbData && Object.keys(kbData).length > 0 ? (
            // Two-pane viewer for KB prompts
            <div style={styles.paneContainer}>
              <div style={styles.leftPane}>
                <div style={styles.leftHeader}>
                  <span>Knowledge Base Prompts</span>
                </div>
                <div style={styles.leftList}>
                  {Object.keys(kbData).map((name) => (
                    <div
                      key={name}
                      onClick={() => setSelectedPromptName(name)}
                      style={name === selectedPromptName ? styles.listItemActive : styles.listItem}
                      title={name}
                    >
                      {name}
                    </div>
                  ))}
                </div>
              </div>
              <div style={styles.rightPane}>
                <div style={styles.rightHeader}>
                  {selectedPromptName || 'No prompt selected'}
                </div>
                <div style={styles.viewer}>
                  {selectedPromptName && kbData[selectedPromptName] ? (
                    <div className="markdownContainer" style={styles.markdownContainer}>
                      <ReactMarkdown>{kbData[selectedPromptName]}</ReactMarkdown>
                    </div>
                  ) : (
                    <div>No prompt selected</div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            // No KB data available
            <div style={styles.emptyStateMessage}>
              <div style={styles.emptyStateIcon}>📝</div>
              <div style={styles.emptyStateText}>No compose output yet</div>
              <div style={styles.emptyStateSubtext}>
                Run Compose from the Compose tab to generate output
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

const styles = {
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
  composeBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    marginBottom: 16
  },
  runStatus: {
    color: '#666'
  },
  composeButton: {
    padding: '10px 20px',
    backgroundColor: '#16a34a',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: '500',
  },
  composeButtonDisabled: {
    padding: '10px 20px',
    backgroundColor: '#d1d5db',
    color: '#6b7280',
    border: 'none',
    borderRadius: '6px',
    cursor: 'not-allowed',
    fontSize: '14px',
    fontWeight: '500',
  },
  contentArea: {
    marginTop: '20px',
    padding: '20px',
    backgroundColor: '#f9fafb',
    borderRadius: '8px',
    border: '1px solid #e5e7eb',
  },
  contentTitle: {
    fontSize: '18px',
    fontWeight: '600',
    marginBottom: '15px',
    color: '#1f2937',
  },
  unitsList: {
    maxHeight: '500px',
    overflowY: 'auto',
  },
  unitContainer: {
    borderBottom: '1px solid #e5e7eb',
  },
  unitItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '6px 12px',
  },
  unitLabelArea: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flex: 1,
    cursor: 'pointer',
    transition: 'background-color 0.15s',
    padding: '4px',
    marginLeft: '-4px',
    borderRadius: '4px',
  },
  checkbox: {
    width: '18px',
    height: '18px',
    cursor: 'pointer',
  },
  unitLabel: {
    fontSize: '14px',
    lineHeight: '1.5',
    color: '#374151',
    flex: 1,
  },
  chevronIcon: {
    fontSize: '12px',
    color: '#6b7280',
    width: '16px',
    display: 'inline-block',
    transition: 'transform 0.2s',
    userSelect: 'none',
  },
  fileLabel: {
    color: '#6b7280',
    fontSize: '13px',
  },
  expandedContent: {
    padding: '16px',
    paddingLeft: '48px',
    backgroundColor: '#f9fafb',
    borderTop: '1px solid #e5e7eb',
    fontSize: '14px',
    color: '#1f2937',
    maxHeight: '400px',
    overflowY: 'auto',
  },
  bodyText: {
    lineHeight: '1.6',
    wordWrap: 'break-word',
  },
  jsonField: {
    marginBottom: '16px',
  },
  jsonKey: {
    fontWeight: '600',
    color: '#059669',
    marginBottom: '6px',
    fontSize: '14px',
  },
  jsonValueContainer: {
    paddingLeft: '0px',
  },
  jsonValue: {
    color: '#1f2937',
    lineHeight: '1.6',
  },
  emptyMessage: {
    padding: '40px',
    textAlign: 'center',
    color: '#6b7280',
    fontSize: '14px',
  },
  loading: {
    padding: '20px',
    textAlign: 'center',
    color: '#6b7280',
  },
  outputContainer: {
    display: 'flex',
    flexDirection: 'column',
    height: '70vh',
    border: '1px solid #e2e2e2',
    borderRadius: 8,
    overflow: 'hidden'
  },
  outputHeader: {
    padding: '8px 12px',
    background: '#fafafa',
    borderBottom: '1px solid #eee',
    fontWeight: 500,
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  copyButton: {
    padding: '6px 12px',
    backgroundColor: '#2563eb',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '13px',
    fontWeight: '500',
    transition: 'background-color 0.2s',
  },
  outputBox: {
    flex: 1,
    overflow: 'auto',
    padding: 20,
    background: '#ffffff',
  },
  markdownContainer: {
    margin: 0,
    fontSize: 16,
    lineHeight: 1.6,
    color: '#1f2937',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  },
  generatingMessage: {
    padding: '40px',
    textAlign: 'center',
    color: '#6b7280',
    fontSize: '16px',
  },
  emptyStateMessage: {
    padding: '60px 40px',
    textAlign: 'center',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '16px',
  },
  emptyStateIcon: {
    fontSize: '48px',
    marginBottom: '8px',
  },
  emptyStateText: {
    fontSize: '18px',
    fontWeight: '600',
    color: '#374151',
  },
  emptyStateSubtext: {
    fontSize: '14px',
    color: '#6b7280',
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
    background: '#fafafa',
    fontSize: 14
  },
  leftList: {
    overflow: 'auto'
  },
  listItem: {
    padding: '8px 12px',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    fontSize: 13
  },
  listItemActive: {
    padding: '8px 12px',
    cursor: 'pointer',
    background: '#eef3ff',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    fontSize: 13
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
    textOverflow: 'ellipsis',
    fontSize: 13,
    fontWeight: 500
  },
  viewer: {
    height: 520,
    overflow: 'auto',
    padding: 12
  },
};
