import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const runtime = 'nodejs';

export async function GET() {
  try {
    const projectName = process.env.PROJECT_NAME || 'Socratic Project';
    const webCwd = process.cwd();
    const repoRoot = path.resolve(webCwd, '..');
    const projectDir = path.join(repoRoot, 'projects', projectName);
    const kbDir = path.join(projectDir, 'knowledge_base');

    // Check if knowledge_base directory exists
    try {
      await fs.promises.access(kbDir);
    } catch {
      return NextResponse.json({ exists: false, files: [] }, { status: 200 });
    }

    // Read all files from the knowledge_base directory
    const entries = await fs.promises.readdir(kbDir, { withFileTypes: true });
    
    // Filter for markdown files only
    const mdFiles = entries
      .filter(entry => entry.isFile() && entry.name.endsWith('.md'))
      .map(entry => path.join(kbDir, entry.name));
    
    return NextResponse.json({ exists: mdFiles.length > 0, files: mdFiles }, { status: 200 });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to read knowledge base' }, { status: 500 });
  }
}

