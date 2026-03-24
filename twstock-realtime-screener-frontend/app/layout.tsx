import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '台股選股系統',
  description: '使用 FastAPI + Next.js 製作的簡易台股選股系統',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant">
      <body className="antialiased bg-gray-50 text-gray-900">
        {children}
      </body>
    </html>
  );
}