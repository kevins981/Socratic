import { NextResponse } from 'next/server';
import { readFile } from 'fs/promises';
import path from 'path';

export const runtime = 'nodejs';

export async function GET() {
  try {
    const projectName = process.env.PROJECT_NAME || 'Socratic Project';
    const webCwd = process.cwd();
    const repoRoot = path.resolve(webCwd, '..');
    const projectDir = path.join(repoRoot, 'projects', projectName);
    const kbFilePath = path.join(projectDir, 'socratic_kbs.json');

    // Try to read the socratic_kbs.json file
    try {
      const content = await readFile(kbFilePath, 'utf-8');
      const kbData = JSON.parse(content);
      return NextResponse.json({ kbData });
    } catch (err) {
      if (err.code === 'ENOENT') {
        return NextResponse.json({ error: 'KB file not found', notFound: true }, { status: 404 });
      }
      return NextResponse.json({ error: `Failed to read KB file: ${err.message}` }, { status: 500 });
    }
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to get KB data' }, { status: 500 });
  }
}

