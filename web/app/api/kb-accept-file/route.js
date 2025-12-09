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

export async function POST(req) {
  try {
    const body = await req.json();
    const { filename } = body;

    if (!filename) {
      return NextResponse.json({ error: 'Missing filename' }, { status: 400 });
    }

    const projectName = process.env.PROJECT_NAME || 'Socratic Project';
    const webCwd = process.cwd();
    const repoRoot = path.resolve(webCwd, '..');
    const projectDir = path.join(repoRoot, 'projects', projectName);
    const projectYamlPath = path.join(projectDir, 'project.yaml');

    // Read project config to get inputDir
    if (!fs.existsSync(projectYamlPath)) {
      return NextResponse.json({ error: 'Project configuration not found' }, { status: 404 });
    }

    const configContent = await fs.promises.readFile(projectYamlPath, 'utf8');
    const projectData = parseSimpleYaml(configContent);

    if (!projectData.input_dir) {
      return NextResponse.json({ error: 'input_dir not found in project configuration' }, { status: 500 });
    }

    // Define paths
    const userKbDir = path.join(projectDir, 'knowledge_base');
    const agentKbDir = path.join(projectData.input_dir, 'knowledge_base');
    const userFilePath = path.join(userKbDir, filename);
    const agentFilePath = path.join(agentKbDir, filename);

    // Security check: ensure filename doesn't contain path traversal
    if (filename.includes('..') || filename.includes('/') || filename.includes('\\')) {
      return NextResponse.json({ error: 'Invalid filename' }, { status: 400 });
    }

    // Ensure user KB directory exists
    if (!fs.existsSync(userKbDir)) {
      await fs.promises.mkdir(userKbDir, { recursive: true });
    }

    // Check if agent file exists
    if (fs.existsSync(agentFilePath)) {
      // Copy agent file to user KB (accept the change)
      const content = await fs.promises.readFile(agentFilePath, 'utf8');
      await fs.promises.writeFile(userFilePath, content, 'utf8');
    } else {
      // Agent deleted the file, so delete from user KB too
      if (fs.existsSync(userFilePath)) {
        await fs.promises.unlink(userFilePath);
      }
    }

    return NextResponse.json({ success: true, action: 'accepted', filename });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to accept file' }, { status: 500 });
  }
}

