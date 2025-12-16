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

function getProjectConfig() {
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

  return { projectName, projectData, projectDir };
}

export async function GET() {
  try {
    const { projectName, projectData } = getProjectConfig();

    if (!projectData.input_dir) {
      return NextResponse.json({ error: 'input_dir not found in project configuration' }, { status: 500 });
    }

    const kbDir = path.join(projectData.input_dir, 'knowledge_base');

    // Check if knowledge_base directory exists
    if (!fs.existsSync(kbDir)) {
      return NextResponse.json({ error: 'Knowledge base directory not found' }, { status: 404 });
    }

    // Read all markdown files from the knowledge_base directory
    const entries = await fs.promises.readdir(kbDir, { withFileTypes: true });
    const mdFiles = entries
      .filter(entry => entry.isFile() && entry.name.endsWith('.md'))
      .sort((a, b) => a.name.localeCompare(b.name));

    if (mdFiles.length === 0) {
      return NextResponse.json({ error: 'No markdown files found in knowledge base' }, { status: 404 });
    }

    // Concatenate all markdown files with newlines between them
    const contentParts = [];
    for (const file of mdFiles) {
      const filePath = path.join(kbDir, file.name);
      const content = await fs.promises.readFile(filePath, 'utf8');
      contentParts.push(content);
    }

    const combinedContent = contentParts.join('\n');

    // Generate timestamp in ISO 8601 format (safe for filenames)
    const timestamp = new Date().toISOString().replace(/:/g, '-').replace(/\.\d{3}Z$/, '');
    const filename = `${projectName}_${timestamp}.md`;

    // Return as downloadable file
    return new Response(combinedContent, {
      status: 200,
      headers: {
        'Content-Type': 'text/markdown; charset=utf-8',
        'Content-Disposition': `attachment; filename="${filename}"`,
      },
    });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to export knowledge base' }, { status: 500 });
  }
}
