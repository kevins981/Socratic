import './globals.css';
import Link from 'next/link';
import { SelectedFilesProvider } from './selected-files-context';

export default function RootLayout({ children }) {
  const projectName = process.env.PROJECT_NAME || 'Socratic Project';
  return (
    <html lang="en">
      <body>
        <SelectedFilesProvider>
          <div className="app">
            <div className="topbar">{projectName}</div>
            <div className="content">
              <aside className="sidebar">
                <nav className="nav">
                  <Link href="/synthesize">Synthesize</Link>
                  <Link href="/compose">Compose</Link>
                </nav>
              </aside>
              <main className="main">{children}</main>
            </div>
          </div>
        </SelectedFilesProvider>
      </body>
    </html>
  );
}


