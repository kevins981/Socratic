import { triageSessionStore } from '../sessionStore';
import { TransformStream } from 'stream/web';

export const runtime = 'nodejs';

export async function GET(req) {
  const { searchParams } = new URL(req.url);
  const sessionId = (searchParams.get('session') || '').trim();
  if (!sessionId) {
    return new Response('Missing session', { status: 400 });
  }
  const sess = triageSessionStore.getSession(sessionId);
  if (!sess) {
    return new Response('Invalid session', { status: 404 });
  }

  const stream = new TransformStream();
  const writer = stream.writable.getWriter();
  const encoder = new TextEncoder();

  // Heartbeat to keep connection alive
  let interval = null;
  const write = (s) => writer.write(encoder.encode(s));
  try {
    // SSE headers and initial replay
    const existing = triageSessionStore.getLogs(sessionId);
    for (const line of existing) {
      write(`data: ${JSON.stringify({ type: 'log', line })}\n\n`);
    }
    write(`data: ${JSON.stringify({ type: 'status', status: sess.status })}\n\n`);

    triageSessionStore.addClient(sessionId, writer);

    interval = setInterval(() => {
      try { write(': keep-alive\n\n'); } catch {}
    }, 20000);
  } catch {
    // ignore
  }

  const close = () => {
    try { clearInterval(interval); } catch {}
    try { triageSessionStore.removeClient(sessionId, writer); } catch {}
    try { writer.close(); } catch {}
  };

  // Close on connection abort
  const abort = req.signal;
  if (abort) {
    abort.addEventListener('abort', close);
  }

  return new Response(stream.readable, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no'
    }
  });
}
