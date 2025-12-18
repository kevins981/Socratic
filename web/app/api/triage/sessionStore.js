import { randomUUID } from 'crypto';

class TriageSessionStore {
  constructor() {
    this.sessions = new Map(); // sessionId -> { child, logs: string[], clients: Set<WritableStreamDefaultWriter>, status }
  }

  createSession(child) {
    const id = randomUUID();
    this.sessions.set(id, { child, logs: [], clients: new Set(), status: 'running' });
    return id;
  }

  getSession(id) {
    return this.sessions.get(id) || null;
  }

  appendLog(id, line) {
    const sess = this.sessions.get(id);
    if (!sess) return;
    sess.logs.push(line);
    const payload = JSON.stringify({ type: 'log', line });
    const data = `data: ${payload}\n\n`;
    for (const writer of sess.clients) {
      try {
        writer.write(new TextEncoder().encode(data));
      } catch {}
    }
  }

  setStatus(id, status, code = null) {
    const sess = this.sessions.get(id);
    if (!sess) return;
    sess.status = status;
    const payload = JSON.stringify({ type: 'status', status, code });
    const data = `data: ${payload}\n\n`;
    for (const writer of sess.clients) {
      try {
        writer.write(new TextEncoder().encode(data));
      } catch {}
    }
  }

  addClient(id, writer) {
    const sess = this.sessions.get(id);
    if (!sess) return false;
    sess.clients.add(writer);
    return true;
  }

  removeClient(id, writer) {
    const sess = this.sessions.get(id);
    if (!sess) return;
    sess.clients.delete(writer);
  }

  getLogs(id) {
    const sess = this.sessions.get(id);
    return sess ? sess.logs.slice() : [];
  }

  dispose(id) {
    const sess = this.sessions.get(id);
    if (!sess) return;
    try {
      if (sess.child && !sess.child.killed) sess.child.kill();
    } catch {}
    this.sessions.delete(id);
  }
}

// Ensure a single global instance across HMR/reloads in dev
const g = globalThis;
if (!g.__socraticTriageSessionStore) {
  g.__socraticTriageSessionStore = new TriageSessionStore();
}
export const triageSessionStore = g.__socraticTriageSessionStore;
