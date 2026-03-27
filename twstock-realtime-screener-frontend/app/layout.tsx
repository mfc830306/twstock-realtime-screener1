import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "台股即時選股系統",
  description: "TWSE 上市股票分類、搜尋、推薦排序與進出場規劃",
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
