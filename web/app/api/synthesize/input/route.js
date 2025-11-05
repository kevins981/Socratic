import { NextResponse } from 'next/server';
import { synthesizeSessionStore } from '../sessionStore';

export const runtime = 'nodejs';

export async function POST(req) {
  try {
    const body = await req.json();
    const sessionId = (body?.sessionId || '').trim();
    const text = body?.text ?? '';
    if (!sessionId) {
      return NextResponse.json({ error: 'Missing sessionId' }, { status: 400 });
    }
    const sess = synthesizeSessionStore.getSession(sessionId);
    if (!sess || !sess.child) {
      return NextResponse.json({ error: 'Invalid session' }, { status: 404 });
    }
    try {
      sess.child.stdin.write(String(text) + '\n');
    } catch (err) {
      return NextResponse.json({ error: err?.message || 'Failed to write to process' }, { status: 500 });
    }
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to submit input' }, { status: 500 });
  }
}

