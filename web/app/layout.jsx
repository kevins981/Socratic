import './globals.css';
import { SelectedFilesProvider } from './selected-files-context';

export default function RootLayout({ children }) {
  const projectName = process.env.PROJECT_NAME || 'Socratic Project';
  
  return (
    <html lang="en">
      <body>
        <SelectedFilesProvider>
          <div className="app">
            <div className="topbar">{projectName}</div>
            <main className="main-content">{children}</main>
          </div>
        </SelectedFilesProvider>
      </body>
    </html>
  );
}
