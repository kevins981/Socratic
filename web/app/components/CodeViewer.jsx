"use client";

import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

// Map file extensions to language names for syntax highlighting
const extensionToLanguage = {
  '.js': 'javascript',
  '.jsx': 'jsx',
  '.ts': 'typescript',
  '.tsx': 'tsx',
  '.py': 'python',
  '.json': 'json',
  '.md': 'markdown',
  '.css': 'css',
  '.scss': 'scss',
  '.html': 'html',
  '.xml': 'xml',
  '.yaml': 'yaml',
  '.yml': 'yaml',
  '.sh': 'bash',
  '.bash': 'bash',
  '.sql': 'sql',
  '.java': 'java',
  '.c': 'c',
  '.cpp': 'cpp',
  '.h': 'c',
  '.hpp': 'cpp',
  '.go': 'go',
  '.rs': 'rust',
  '.rb': 'ruby',
  '.php': 'php',
  '.swift': 'swift',
  '.kt': 'kotlin',
  '.scala': 'scala',
  '.r': 'r',
  '.R': 'r',
  '.txt': 'text',
  '.log': 'text',
  '.env': 'bash',
  '.gitignore': 'text',
  '.dockerignore': 'text',
  '.toml': 'toml',
  '.ini': 'ini',
  '.cfg': 'ini',
};

function getLanguageFromFilename(filename) {
  if (!filename) return 'text';
  
  // Get the extension
  const lastDot = filename.lastIndexOf('.');
  if (lastDot === -1) return 'text';
  
  const ext = filename.substring(lastDot).toLowerCase();
  return extensionToLanguage[ext] || 'text';
}

export default function CodeViewer({ content, filename }) {
  const language = getLanguageFromFilename(filename);

  // Custom style overrides to match existing theme
  const customStyle = {
    ...vscDarkPlus,
    'pre[class*="language-"]': {
      ...vscDarkPlus['pre[class*="language-"]'],
      margin: 0,
      padding: '16px',
      background: '#1e1e1e',
      fontSize: '13px',
      lineHeight: '1.5',
    },
    'code[class*="language-"]': {
      ...vscDarkPlus['code[class*="language-"]'],
      fontSize: '13px',
      lineHeight: '1.5',
    },
  };

  return (
    <SyntaxHighlighter
      language={language}
      style={customStyle}
      showLineNumbers={true}
      wrapLines={true}
      wrapLongLines={true}
      lineNumberStyle={{
        minWidth: '3em',
        paddingRight: '1em',
        color: '#6e7681',
        textAlign: 'right',
        userSelect: 'none',
        borderRight: '1px solid #3c3c3c',
        marginRight: '1em',
      }}
      customStyle={{
        margin: 0,
        padding: 0,
        background: '#1e1e1e',
        height: '100%',
        overflow: 'auto',
      }}
    >
      {content || ''}
    </SyntaxHighlighter>
  );
}
