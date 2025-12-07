import { NextResponse } from 'next/server';
import { synthesizeSessionStore } from '../sessionStore';

export const runtime = 'nodejs';

export async function POST(req) {
  try {
    const body = await req.json();
    const sessionId = (body?.sessionId || '').trim();
    
    if (!sessionId) {
      return NextResponse.json({ error: 'Missing sessionId' }, { status: 400 });
    }
    
    const sess = synthesizeSessionStore.getSession(sessionId);
    if (!sess) {
      return NextResponse.json({ error: 'Session not found' }, { status: 404 });
    }
    
    synthesizeSessionStore.dispose(sessionId);
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to stop session' }, { status: 500 });
  }
}

