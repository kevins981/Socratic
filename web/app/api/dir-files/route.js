import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

async function listFilesRecursive(rootDir) {
  const results = [];
  async function walk(currentDir) {
    const entries = await fs.promises.readdir(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      // Skip .socratic directory
      if (entry.name === '.socratic') {
        continue;
      }
      // Skip knowledge_base metadata directory
      if (entry.isDirectory() && entry.name === 'knowledge_base') {
        continue;
      }
      const entryPath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        await walk(entryPath);
      } else if (entry.isFile()) {
        results.push(entryPath);
      }
    }
  }
  await walk(rootDir);
  return results.sort();
}

export async function GET(req) {
  try {
    const { searchParams } = new URL(req.url);
    const inputDir = (searchParams.get('dir') || '').trim();
    if (!inputDir) {
      return NextResponse.json({ error: 'Missing dir parameter' }, { status: 400 });
    }

    const absDir = path.resolve(inputDir);
    const stat = await fs.promises.stat(absDir);
    if (!stat.isDirectory()) {
      return NextResponse.json({ error: 'Not a directory' }, { status: 400 });
    }

    const files = await listFilesRecursive(absDir);
    return NextResponse.json({ files });
  } catch (err) {
    const status = err && err.code === 'ENOENT' ? 404 : 500;
    return NextResponse.json({ error: err?.message || 'Failed to list directory files' }, { status });
  }
}


