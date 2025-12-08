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

    // Ensure agent KB directory exists
    if (!fs.existsSync(agentKbDir)) {
      await fs.promises.mkdir(agentKbDir, { recursive: true });
    }

    // Check if user file exists
    if (fs.existsSync(userFilePath)) {
      // Copy user file to agent KB (reject the change, revert agent's copy)
      const content = await fs.promises.readFile(userFilePath, 'utf8');
      await fs.promises.writeFile(agentFilePath, content, 'utf8');
    } else {
      // User doesn't have the file, so delete from agent KB too
      if (fs.existsSync(agentFilePath)) {
        await fs.promises.unlink(agentFilePath);
      }
    }

    return NextResponse.json({ success: true, action: 'rejected', filename });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to reject file' }, { status: 500 });
  }
}

