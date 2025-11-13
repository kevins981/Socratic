import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

export const runtime = 'nodejs';

export async function POST(req) {
  try {
    const body = await req.json();
    const conceptId = body?.conceptId;
    
    if (conceptId === undefined || conceptId === null) {
      return NextResponse.json({ error: 'Missing conceptId' }, { status: 400 });
    }

    const projectName = process.env.PROJECT_NAME || 'Socratic Project';
    // Compute repo root assuming this file is under <repo>/web/app/api/...
    const webCwd = process.cwd();
    const repoRoot = path.resolve(webCwd, '..');

    const args = [
      '-m', 'socratic.cli', 'synth',
      '--model', 'gpt-5',
      '--project', projectName,
      '--delete_concept', String(conceptId)
    ];
    
    return new Promise((resolve) => {
      const child = spawn('python3', args, {
        cwd: repoRoot,
        env: { ...process.env },
        stdio: ['pipe', 'pipe', 'pipe']
      });

      let stdout = '';
      let stderr = '';

      child.stdout.on('data', (chunk) => {
        stdout += chunk.toString();
      });

      child.stderr.on('data', (chunk) => {
        stderr += chunk.toString();
      });

      child.on('exit', (code) => {
        if (code === 0) {
          resolve(NextResponse.json({ success: true }));
        } else {
          resolve(NextResponse.json({ 
            error: `Delete failed with code ${code}`, 
            details: stderr || stdout 
          }, { status: 500 }));
        }
      });

      child.on('error', (err) => {
        resolve(NextResponse.json({ 
          error: err?.message || 'Failed to execute delete command' 
        }, { status: 500 }));
      });
    });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to delete concept' }, { status: 500 });
  }
}

