"use client";

/**
 * 品牌标识（BrandMark）。
 *
 * 为什么要单独一个组件
 * --------------------
 * 之前顶栏用的是 `IconTaiji` —— 那是**功能图标**（线性、等宽描边、1em 语义），
 * 把它放大当品牌标会同时毁掉两件事：图标在 20px 下的清晰度，和品牌标需要的
 * 实心层次。按用户要求，三者分开设计：
 *
 * 1. `BrandMark`（本文件）—— 品牌标：实心阴阳 + 笔触外圈 + 金色层次；
 * 2. `Astrolabe`（`shell/Decorations.tsx`）—— 页面装饰星盘；
 * 3. `Icons.tsx` —— 功能图标（线性、单色、跟随 currentColor）。
 *
 * 关于"还原度"的诚实说明
 * ----------------------
 * 参考图里的品牌标是**手绘笔触**风格（外圈粗细不均、阴阳体整体倾斜），
 * 且没有随图提供原始 Logo 文件。本组件是按参考图的构图与配色**自绘**的矢量版本：
 * 实心双色阴阳体 + 不均笔触外圈 + 金色渐变，不是对原图的描摹、也不是位图切片。
 * 与参考图的残余差异（笔触细节、外圈断口位置）在交付报告中如实列出。
 */

import React, { useId } from "react";

/** 太极主体半径与圆心（viewBox 48×48） */
const CX = 24;
const CY = 24;
const R = 17.2;
/** 阴阳体整体倾斜角（参考图中并非正立，而是顺时针略转） */
const TILT = 24;

/** 外圈笔触：5 段弧、粗细与透明度各不相同，段间刻意重叠以形成"一笔画圈"的手感 */
const RING_RADIUS = 20.9;
const RING_SEGMENTS: ReadonlyArray<{
  d: string;
  width: number;
  opacity: number;
}> = [
  { d: "M 20.37 3.42 A 20.9 20.9 0 0 1 40.01 37.43", width: 2.6, opacity: 0.95 },
  { d: "M 41.33 35.69 A 20.9 20.9 0 0 1 7.53 36.87", width: 1.8, opacity: 0.78 },
  { d: "M 8.97 38.52 A 20.9 20.9 0 0 1 18.94 3.72", width: 3.0, opacity: 0.92 },
  { d: "M 16.85 4.36 A 20.9 20.9 0 0 1 44.58 20.37", width: 1.5, opacity: 0.7 },
  { d: "M 44.09 18.24 A 20.9 20.9 0 0 1 44.79 26.18", width: 2.2, opacity: 0.9 },
];

export function BrandMark({
  size = 38,
  className = "",
  title = "股票玄学多模型研究平台",
  testId = "brand-mark",
}: {
  size?: number;
  className?: string;
  title?: string;
  testId?: string;
}) {
  // 渐变 id 必须唯一：同一页面可能同时出现顶栏与页脚两个品牌标
  const uid = useId().replace(/[:]/g, "");
  const goldId = `bm-gold-${uid}`;
  const darkId = `bm-dark-${uid}`;
  const glowId = `bm-glow-${uid}`;

  // --- 太极主体：两个严格互补的实心半体（拼接无缝，避免出现一条缝） ---
  const lightHalf = [
    `M ${CX} ${CY - R}`,
    `A ${R} ${R} 0 0 1 ${CX} ${CY + R}`,
    `A ${R / 2} ${R / 2} 0 0 1 ${CX} ${CY}`,
    `A ${R / 2} ${R / 2} 0 0 0 ${CX} ${CY - R}`,
    "Z",
  ].join(" ");
  const darkHalf = [
    `M ${CX} ${CY - R}`,
    `A ${R} ${R} 0 0 0 ${CX} ${CY + R}`,
    `A ${R / 2} ${R / 2} 0 0 0 ${CX} ${CY}`,
    `A ${R / 2} ${R / 2} 0 0 1 ${CX} ${CY - R}`,
    "Z",
  ].join(" ");

  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center ${className}`}
      style={{ width: size, height: size }}
      data-testid={testId}
      data-brand-mark-version="brand-mark-v1"
    >
      <svg
        viewBox="0 0 48 48"
        width={size}
        height={size}
        role="img"
        aria-label={title}
        className="overflow-visible"
      >
        <defs>
          <linearGradient id={goldId} x1="18%" y1="6%" x2="86%" y2="96%">
            <stop offset="0%" stopColor="#f6ead0" />
            <stop offset="34%" stopColor="#e2c893" />
            <stop offset="68%" stopColor="#cfa963" />
            <stop offset="100%" stopColor="#9d8248" />
          </linearGradient>
          <linearGradient id={darkId} x1="20%" y1="10%" x2="82%" y2="92%">
            <stop offset="0%" stopColor="#14242f" />
            <stop offset="55%" stopColor="#0b1721" />
            <stop offset="100%" stopColor="#060f16" />
          </linearGradient>
          <radialGradient id={glowId} cx="50%" cy="46%" r="56%">
            <stop offset="0%" stopColor="#e2c893" stopOpacity="0.24" />
            <stop offset="60%" stopColor="#cfa963" stopOpacity="0.06" />
            <stop offset="100%" stopColor="#cfa963" stopOpacity="0" />
          </radialGradient>
        </defs>

        <g
          fill="none"
          stroke={`url(#${goldId})`}
          strokeLinecap="round"
          transform={`rotate(-8 ${CX} ${CY})`}
        >
          {RING_SEGMENTS.map((seg, i) => (
            <path
              key={i}
              d={seg.d}
              strokeWidth={seg.width}
              opacity={seg.opacity}
            />
          ))}
        </g>

        {/* 阴阳体（整体倾斜，与参考图一致） */}
        <g transform={`rotate(${TILT} ${CX} ${CY})`}>
          <circle cx={CX} cy={CY} r={19.4} fill={`url(#${glowId})`} />
          <path d={darkHalf} fill={`url(#${darkId})`} />
          {/* 暗半的浅色描边：参考图中阴面边缘有一道米金色轮廓 */}
          <path
            d={darkHalf}
            fill="none"
            stroke="#cfa963"
            strokeOpacity={0.42}
            strokeWidth={0.7}
          />
          <path d={lightHalf} fill={`url(#${goldId})`} />
          {/* 阳中之阴 / 阴中之阳 */}
          <circle cx={CX} cy={CY - R / 2} r={R / 6.4} fill="#f4e7cb" />
          <circle cx={CX} cy={CY + R / 2} r={R / 6.4} fill="#0a1520" />
        </g>
      </svg>
    </span>
  );
}

export default BrandMark;
