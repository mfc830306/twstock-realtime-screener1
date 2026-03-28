import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "台股分類瀏覽",
  description: "台股分類、搜尋、排序與推薦",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
