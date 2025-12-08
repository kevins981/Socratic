import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const runtime = 'nodejs';

// Simple YAML parser for basic key: value format
function parseSimpleYaml(content) {
  const result = {};
  const lines = content.split('\n');

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const colonIndex = trimmed.indexOf(':');
    if (colonIndex === -1) continue;

    const key = trimmed.substring(0, colonIndex).trim();
    const value = trimmed.substring(colonIndex + 1).trim();

    if (key && value) {
      result[key] = value;
    }
  }

  return result;
}

function getKbDirs() {
  const projectName = process.env.PROJECT_NAME || 'Socratic Project';
  const webCwd = process.cwd();
  const repoRoot = path.resolve(webCwd, '..');
  const projectDir = path.join(repoRoot, 'projects', projectName);
  const projectYamlPath = path.join(projectDir, 'project.yaml');

  if (!fs.existsSync(projectYamlPath)) {
    throw new Error('Project configuration not found');
  }

  const configContent = fs.readFileSync(projectYamlPath, 'utf8');
  const projectData = parseSimpleYaml(configContent);

  if (!projectData.input_dir) {
    throw new Error('input_dir not found in project configuration');
  }

  const agentKbDir = path.join(projectData.input_dir, 'knowledge_base');
  const userKbDir = path.join(projectDir, 'knowledge_base');

  return { agentKbDir, userKbDir };
}

export async function GET() {
  try {
    const { agentKbDir } = getKbDirs();

    // Check if knowledge_base directory exists
    try {
      await fs.promises.access(agentKbDir);
    } catch {
      return NextResponse.json({ exists: false, files: [] }, { status: 200 });
    }

    // Read all files from the knowledge_base directory
    const entries = await fs.promises.readdir(agentKbDir, { withFileTypes: true });
    
    // Filter for markdown files only
    const mdFiles = entries
      .filter(entry => entry.isFile() && entry.name.endsWith('.md'))
      .map(entry => path.join(agentKbDir, entry.name));
    
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

    const { agentKbDir, userKbDir } = getKbDirs();
    const resolvedAgentPath = path.resolve(filePath);
    const normalizedAgentDir = path.resolve(agentKbDir);

    // Security check: ensure the file is within the knowledge_base directory
    if (
      resolvedAgentPath !== normalizedAgentDir &&
      !resolvedAgentPath.startsWith(normalizedAgentDir + path.sep)
    ) {
      return NextResponse.json({ error: 'Invalid file path' }, { status: 400 });
    }

    // Write to agent KB
    await fs.promises.writeFile(resolvedAgentPath, content, 'utf8');

    // Mirror to user KB (same relative path)
    const relativePath = path.relative(normalizedAgentDir, resolvedAgentPath);
    if (relativePath.startsWith('..') || path.isAbsolute(relativePath)) {
      return NextResponse.json({ error: 'Invalid relative path' }, { status: 400 });
    }

    const normalizedUserDir = path.resolve(userKbDir);
    const resolvedUserPath = path.join(normalizedUserDir, relativePath);

    // Ensure target directory exists
    await fs.promises.mkdir(path.dirname(resolvedUserPath), { recursive: true });

    // Write to user KB
    await fs.promises.writeFile(resolvedUserPath, content, 'utf8');
    
    return NextResponse.json({ success: true }, { status: 200 });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to save file' }, { status: 500 });
  }
}
