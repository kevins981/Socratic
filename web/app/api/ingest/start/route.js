import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';
import { ingestSessionStore } from '../sessionStore';

export const runtime = 'nodejs';

export async function POST(req) {
  try {
    const body = await req.json();
    const inputDir = (body?.inputDir || '').trim();
    if (!inputDir) {
      return NextResponse.json({ error: 'Missing inputDir' }, { status: 400 });
    }

    const projectName = process.env.PROJECT_NAME || 'Socratic Project';
    // Compute repo root assuming this file is under <repo>/web/app/api/...
    const webCwd = process.cwd();
    const repoRoot = path.resolve(webCwd, '..');

    const args = ['-m', 'socratic.cli', 'ingest', '--model', 'gpt-5-mini', '--input_dir', inputDir, '--project', projectName];
    const child = spawn('python3', args, {
      cwd: repoRoot,
      env: { ...process.env },
      stdio: ['pipe', 'pipe', 'pipe']
    });

    const sessionId = ingestSessionStore.createSession(child);
    ingestSessionStore.appendLog(sessionId, `[INFO] Ingest session started. Launching: python3 ${args.join(' ')}`);

    const handleData = (chunk, isErr = false) => {
      const text = chunk.toString();
      // Split into lines but keep partials simple
      text.split('\n').forEach((line, idx, arr) => {
        const actual = idx < arr.length - 1 ? line : line; // keep last even if empty
        if (actual !== undefined) {
          const prefixed = isErr ? `[ERR] ${actual}` : actual;
          ingestSessionStore.appendLog(sessionId, prefixed);
        }
      });
    };

    child.stdout.on('data', (d) => handleData(d, false));
    child.stderr.on('data', (d) => handleData(d, true));
    child.on('exit', (code) => {
      ingestSessionStore.setStatus(sessionId, 'exited', code ?? 0);
    });
    child.on('error', (err) => {
      ingestSessionStore.appendLog(sessionId, `[ERR] ${err?.message || 'Process error'}`);
      ingestSessionStore.setStatus(sessionId, 'error', null);
    });

    return NextResponse.json({ sessionId });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to start ingest' }, { status: 500 });
  }
}


