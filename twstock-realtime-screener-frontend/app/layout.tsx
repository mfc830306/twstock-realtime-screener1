import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "台股即時選股系統",
  description: "上市 / 上櫃 / ETF 分類、搜尋、推薦排序與進出場規劃",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant">
      <body style={{ minHeight: "100vh", overflow: "hidden" }}>{children}</body>
    </html>
  );
}
