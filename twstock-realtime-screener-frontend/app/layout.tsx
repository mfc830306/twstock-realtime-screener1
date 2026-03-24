import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "台股智慧選股系統",
  description: "台股即時掃描、分類、推薦排序與進出場規劃",
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
