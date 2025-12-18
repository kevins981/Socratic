import { redirect } from 'next/navigation';

export default function Page() {
  const uiMode = process.env.UI_MODE || 'synthesize';
  
  if (uiMode === 'triage') {
    redirect('/triage');
  } else {
    redirect('/synthesize');
  }
}


