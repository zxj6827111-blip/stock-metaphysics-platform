import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "股票玄学多模型研究平台",
  description:
    "传统术数多模型 × 古籍知识库 × 股票历史行情 × 统计回测验证的研究平台。研究实验用途，不构成投资建议。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
