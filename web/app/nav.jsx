'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Nav() {
  const pathname = usePathname();
  
  return (
    <nav className="nav">
      <Link href="/synthesize" className={pathname === '/synthesize' ? 'active' : ''}>Synthesize</Link>
    </nav>
  );
}

