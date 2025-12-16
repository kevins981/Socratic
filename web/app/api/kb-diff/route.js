import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import * as Diff from 'diff';

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

// Compute unified diff between two strings using LCS-based algorithm
function computeUnifiedDiff(oldContent, newContent, filename) {
  // Use diff library to compute proper line-based diff with LCS algorithm
  const changes = Diff.diffLines(oldContent, newContent);
  
  const result = [];
  let oldLineNum = 1;
  let newLineNum = 1;
  
  for (const change of changes) {
    const lines = change.value.split('\n');
    // Remove the last empty line if the value ends with \n
    if (lines[lines.length - 1] === '') {
      lines.pop();
    }
    
    if (change.added) {
      // Lines added in new version
      for (const line of lines) {
        result.push({ type: 'add', line, lineNum: newLineNum });
        newLineNum++;
      }
    } else if (change.removed) {
      // Lines removed from old version
      for (const line of lines) {
        result.push({ type: 'del', line, lineNum: oldLineNum });
        oldLineNum++;
      }
    } else {
      // Unchanged lines (context)
      for (const line of lines) {
        result.push({ type: 'ctx', line, lineNum: newLineNum });
        oldLineNum++;
        newLineNum++;
      }
    }
  }
  
  return result;
}

export async function GET() {
  try {
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

    // Define both KB directories
    const userKbDir = path.join(projectDir, 'knowledge_base');
    const agentKbDir = path.join(projectData.input_dir, 'knowledge_base');

    // Check if directories exist
    const userKbExists = fs.existsSync(userKbDir);
    const agentKbExists = fs.existsSync(agentKbDir);

    if (!userKbExists && !agentKbExists) {
      return NextResponse.json({ changedFiles: [], agentKbDir, userKbDir });
    }

    // Get files from both directories
    const userFiles = new Set();
    const agentFiles = new Set();

    if (userKbExists) {
      const entries = await fs.promises.readdir(userKbDir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isFile() && entry.name.endsWith('.md')) {
          userFiles.add(entry.name);
        }
      }
    }

    if (agentKbExists) {
      const entries = await fs.promises.readdir(agentKbDir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isFile() && entry.name.endsWith('.md')) {
          agentFiles.add(entry.name);
        }
      }
    }

    // Find changes
    const changedFiles = [];

    // Files added by agent (in agent KB but not in user KB)
    for (const filename of agentFiles) {
      if (!userFiles.has(filename)) {
        const agentFilePath = path.join(agentKbDir, filename);
        const newContent = await fs.promises.readFile(agentFilePath, 'utf8');
        changedFiles.push({
          filename,
          status: 'added',
          agentPath: agentFilePath,
          userPath: path.join(userKbDir, filename),
          diff: computeUnifiedDiff('', newContent, filename),
          oldContent: '',
          newContent
        });
      }
    }

    // Files deleted by agent (in user KB but not in agent KB)
    for (const filename of userFiles) {
      if (!agentFiles.has(filename)) {
        const userFilePath = path.join(userKbDir, filename);
        const oldContent = await fs.promises.readFile(userFilePath, 'utf8');
        changedFiles.push({
          filename,
          status: 'deleted',
          agentPath: path.join(agentKbDir, filename),
          userPath: userFilePath,
          diff: computeUnifiedDiff(oldContent, '', filename),
          oldContent,
          newContent: ''
        });
      }
    }

    // Files modified (in both, but different content)
    for (const filename of userFiles) {
      if (agentFiles.has(filename)) {
        const userFilePath = path.join(userKbDir, filename);
        const agentFilePath = path.join(agentKbDir, filename);
        
        const userContent = await fs.promises.readFile(userFilePath, 'utf8');
        const agentContent = await fs.promises.readFile(agentFilePath, 'utf8');
        
        if (userContent !== agentContent) {
          changedFiles.push({
            filename,
            status: 'modified',
            agentPath: agentFilePath,
            userPath: userFilePath,
            diff: computeUnifiedDiff(userContent, agentContent, filename),
            oldContent: userContent,
            newContent: agentContent
          });
        }
      }
    }

    return NextResponse.json({ 
      changedFiles, 
      agentKbDir, 
      userKbDir,
      hasChanges: changedFiles.length > 0
    });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to compute diff' }, { status: 500 });
  }
}

