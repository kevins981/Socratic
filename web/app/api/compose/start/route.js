import { NextResponse } from 'next/server';
import { composeSessionStore } from '../sessionStore.js';
import { spawn } from 'child_process';
import path from 'path';
import { writeFile, mkdtemp, rm } from 'fs/promises';
import { tmpdir } from 'os';
import { DEFAULT_MODEL,  DEFAULT_COMPOSE_MODEL } from '../../../config';

export const runtime = 'nodejs';

export async function POST(req) {
  try {
    const body = await req.json();
    const selectedUnits = body?.selectedUnits;
    
    if (!selectedUnits || !Array.isArray(selectedUnits)) {
      return NextResponse.json({ error: 'Missing or invalid selectedUnits' }, { status: 400 });
    }

    if (selectedUnits.length === 0) {
      return NextResponse.json({ error: 'At least one knowledge unit must be selected' }, { status: 400 });
    }

    const projectName = process.env.PROJECT_NAME || 'Socratic Project';
    const webCwd = process.cwd();
    const repoRoot = path.resolve(webCwd, '..');

    // Create a temporary directory and file for the selected units
    const tempDir = await mkdtemp(path.join(tmpdir(), 'socratic-compose-'));
    const unitsFile = path.join(tempDir, 'selected-units.json');
    await writeFile(unitsFile, JSON.stringify(selectedUnits, null, 2), 'utf-8');

    const args = [
      '-u', // Unbuffered output for real-time streaming
      '-m', 'socratic.cli', 'compose',
      '--project', projectName,
      '--units-json-file', unitsFile
    ];
    
    const child = spawn('python3', args, {
      cwd: repoRoot,
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
      stdio: ['pipe', 'pipe', 'pipe']
    });

    const sessionId = composeSessionStore.createSession(child);
    composeSessionStore.appendLog(sessionId, `[INFO] Compose session started. Launching: python3 ${args.join(' ')}`);

    const handleData = (chunk, isErr = false) => {
      const text = chunk.toString();
      text.split('\n').forEach((line, idx, arr) => {
        const actual = idx < arr.length - 1 ? line : line;
        if (actual !== undefined) {
          const prefixed = isErr ? `[ERR] ${actual}` : actual;
          composeSessionStore.appendLog(sessionId, prefixed);
        }
      });
    };

    child.stdout.on('data', (d) => handleData(d, false));
    child.stderr.on('data', (d) => handleData(d, true));
    child.on('exit', (code) => {
      composeSessionStore.setStatus(sessionId, 'exited', code ?? 0);
      // Clean up temp directory after process completes
      rm(tempDir, { recursive: true, force: true }).catch(() => {});
    });
    child.on('error', (err) => {
      composeSessionStore.appendLog(sessionId, `[ERR] ${err?.message || 'Process error'}`);
      composeSessionStore.setStatus(sessionId, 'error', null);
      // Clean up temp directory on error
      rm(tempDir, { recursive: true, force: true }).catch(() => {});
    });

    return NextResponse.json({ sessionId });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to start compose' }, { status: 500 });
  }
}

