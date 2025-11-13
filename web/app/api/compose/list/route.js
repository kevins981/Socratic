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

    // Look for the consolidated synth file
    const synthFile = 'synth-consolidated.json';
    const synthFilePath = path.join(projectDir, synthFile);

    // Extract knowledge units from the consolidated file
    const allUnits = [];
    try {
      const content = await readFile(synthFilePath, 'utf-8');
      const data = JSON.parse(content);
      
      const knowledgeUnits = data.knowledge_units || [];
      for (const unit of knowledgeUnits) {
        allUnits.push({
          unit: unit,
          conceptFile: synthFile
        });
      }
    } catch (err) {
      if (err.code === 'ENOENT') {
        return NextResponse.json({ error: `Synth file not found: ${synthFile}` }, { status: 404 });
      }
      console.error(`Error processing ${synthFile}:`, err.message);
      return NextResponse.json({ error: `Failed to read synth file: ${err.message}` }, { status: 500 });
    }

    return NextResponse.json({ units: allUnits });
  } catch (err) {
    return NextResponse.json({ error: err?.message || 'Failed to list knowledge units' }, { status: 500 });
  }
}

