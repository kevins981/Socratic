import './globals.css';
import { SelectedFilesProvider } from './selected-files-context';

export default function RootLayout({ children }) {
  const projectName = process.env.PROJECT_NAME || 'Socratic Project';
  const uiMode = process.env.UI_MODE || 'synthesize';
  const headerLabel = uiMode === 'triage' 
    ? `${projectName} — Socratic Triage`
    : projectName;
  
  return (
    <html lang="en">
      <body>
        <SelectedFilesProvider>
          <div className="app">
            <div className="topbar">{headerLabel}</div>
            <main className="main-content">{children}</main>
          </div>
        </SelectedFilesProvider>
      </body>
    </html>
  );
}
