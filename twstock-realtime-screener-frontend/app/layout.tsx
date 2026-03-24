import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '台股即時選股系統',
  description: 'FastAPI + Next.js 台股選股系統（Render 部署版）',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-Hant">
      <body className="bg-gray-50 text-gray-900 antialiased">
        <div className="min-h-screen flex flex-col">
          
          {/* Header */}
          <header className="border-b bg-white">
            <div className="mx-auto max-w-6xl px-6 py-4 flex items-center justify-between">
              <h1 className="text-lg font-bold text-gray-900">
                台股選股系統
              </h1>
              <span className="text-sm text-gray-500">
                Render + Vercel
              </span>
            </div>
          </header>

          {/* Main */}
          <main className="flex-1">
            {children}
          </main>

          {/* Footer */}
          <footer className="border-t bg-white">
            <div className="mx-auto max-w-6xl px-6 py-4 text-sm text-gray-500 text-center">
              © {new Date().getFullYear()} 台股選股系統 | FastAPI + Next.js
            </div>
          </footer>

        </div>
      </body>
    </html>
  );
}