import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const runtime = 'nodejs';

function getKnowledgeBaseDir() {
  const projectName = process.env.PROJECT_NAME || 'Socratic Project';
  const webCwd = process.cwd();
  const repoRoot = path.resolve(webCwd, '..');
  const projectDir = path.join(repoRoot, 'projects', projectName);
  return path.join(projectDir, 'knowledge_base');
}

export async function GET() {
  try {
    const kbDir = getKnowledgeBaseDir();

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

export async function POST(req) {
  try {
    const { path: filePath, content } = await req.json();
    
    if (!filePath || typeof content !== 'string') {
      return NextResponse.json({ error: 'Missing path or content' }, { status: 400 });
    }

    const kbDir = getKnowledgeBaseDir();
    const resolvedPath = path.resolve(filePath);
    const normalizedKbDir = path.resolve(kbDir);

    // Security check: ensure the file is within the knowledge_base directory
    if (!resolvedPath.startsWith(normalizedKbDir + path.sep)) {
      return NextResponse.json({ error: 'Invalid file path' }, { status: 400 });
    }

    // Write the file
    await fs.promises.writeFile(resolvedPath, content, 'utf8');
    
    return NextResponse.json({ success: true }, { status: 200 });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to save file' }, { status: 500 });
  }
}
