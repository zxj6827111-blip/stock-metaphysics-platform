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
      <head>
        {/*
          预加载自托管字体子集。
          为什么必须 preload：字体是 CSS 里通过 @font-face 触发的**迟发现**资源 ——
          浏览器要等 CSSOM 解析完、布局时发现缺字形才开始下载。在深色研究终端里，
          这段窗口会先按回退字体（Windows 上是 SimSun / 雅黑）渲染一次标题，
          造成"首屏字形与参考图不符"的观感差异（也正是上一轮被指出的问题）。
          preload 把它提到与 CSS 同级优先级。
          crossOrigin 必须显式给出，否则会按不同 CORS 模式二次下载。
        */}
        <link
          rel="preload"
          href="/fonts/noto-serif-sc-subset.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
        <link
          rel="preload"
          href="/fonts/noto-sans-sc-subset.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
