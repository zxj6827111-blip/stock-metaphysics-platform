"use client";

/**
 * 东方视觉装饰组件集（纯 SVG 矢量，无外部位图依赖）。
 *
 * 用于提升平台的东方术数识别质感（AGENTS.md §9 规范，比例 20%）。
 * 严禁使用参考图整页切片；全部由确定性参数化矢量渲染。
 */

import React from "react";

/**
 * 天体星盘（Astrolabe）
 * 包含：多重同心星轨、二十八宿分度刻度、十二地支方位标记与核心阴阳太极。
 */
export function Astrolabe({
  size = 260,
  className = "",
  glow = true,
}: {
  size?: number;
  className?: string;
  glow?: boolean;
}) {
  const center = 150;
  // 12 地支标记
  const branches = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"];

  return (
    <div
      className={`relative flex items-center justify-center select-none pointer-events-none ${className}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
      data-testid="astrolabe-ornament"
    >
      <svg
        viewBox="0 0 300 300"
        width={size}
        height={size}
        className="overflow-visible"
      >
        <defs>
          <radialGradient id="astrolabeGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#d4b87a" stopOpacity="0.14" />
            <stop offset="60%" stopColor="#d4b87a" stopOpacity="0.04" />
            <stop offset="100%" stopColor="#d4b87a" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="goldLine" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#ecd79f" stopOpacity="0.6" />
            <stop offset="50%" stopColor="#d4b87a" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#9a8551" stopOpacity="0.5" />
          </linearGradient>
        </defs>

        {glow ? <circle cx={center} cy={center} r={145} fill="url(#astrolabeGlow)" /> : null}

        {/* 最外层：细星轨虚线圈 */}
        <circle
          cx={center}
          cy={center}
          r={140}
          fill="none"
          stroke="var(--color-gold-dim)"
          strokeOpacity={0.25}
          strokeWidth={1}
          strokeDasharray="3 5"
        />

        {/* 次外层：分度刻度圈（24/28宿分度线） */}
        <circle
          cx={center}
          cy={center}
          r={128}
          fill="none"
          stroke="url(#goldLine)"
          strokeWidth={1.2}
          strokeOpacity={0.45}
        />
        {Array.from({ length: 48 }).map((_, i) => {
          const angle = (i * 360) / 48;
          const rad = (angle * Math.PI) / 180;
          const isMajor = i % 4 === 0;
          const r1 = isMajor ? 122 : 125;
          const r2 = 128;
          const x1 = center + r1 * Math.cos(rad);
          const y1 = center + r1 * Math.sin(rad);
          const x2 = center + r2 * Math.cos(rad);
          const y2 = center + r2 * Math.sin(rad);
          return (
            <line
              key={i}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke="var(--color-gold)"
              strokeOpacity={isMajor ? 0.6 : 0.25}
              strokeWidth={isMajor ? 1.2 : 0.8}
            />
          );
        })}

        {/* 十二地支方位环 */}
        <circle
          cx={center}
          cy={center}
          r={105}
          fill="none"
          stroke="var(--color-gold-dim)"
          strokeOpacity={0.3}
          strokeWidth={0.9}
        />
        {branches.map((b, i) => {
          // 子在正上方 (270度 = -90度)
          const angle = (i * 360) / 12 - 90;
          const rad = (angle * Math.PI) / 180;
          const r = 114;
          const x = center + r * Math.cos(rad);
          const y = center + r * Math.sin(rad);
          return (
            <text
              key={b}
              x={x}
              y={y + 3.5}
              textAnchor="middle"
              fill="var(--color-gold)"
              fillOpacity={0.55}
              fontSize={10}
              fontFamily="var(--font-serif-cn)"
              style={{ fontWeight: 500 }}
            >
              {b}
            </text>
          );
        })}

        {/* 内环双轨 */}
        <circle
          cx={center}
          cy={center}
          r={86}
          fill="none"
          stroke="url(#goldLine)"
          strokeWidth={1}
          strokeOpacity={0.35}
        />
        <circle
          cx={center}
          cy={center}
          r={62}
          fill="none"
          stroke="var(--color-gold-dim)"
          strokeWidth={0.8}
          strokeDasharray="2 3"
          strokeOpacity={0.3}
        />

        {/* 星轨天体圆点 */}
        {[-35, 45, 130, 220].map((deg, i) => {
          const rad = (deg * Math.PI) / 180;
          const r = i % 2 === 0 ? 86 : 62;
          const cx = center + r * Math.cos(rad);
          const cy = center + r * Math.sin(rad);
          return (
            <circle
              key={deg}
              cx={cx}
              cy={cy}
              r={i % 2 === 0 ? 2.5 : 2}
              fill="var(--color-gold)"
              fillOpacity={0.7}
            />
          );
        })}

        {/* 核心太极阴阳盘 */}
        <g transform={`translate(${center - 24}, ${center - 24})`}>
          <circle cx={24} cy={24} r={24} fill="#0d1b26" stroke="var(--color-gold)" strokeWidth={1} strokeOpacity={0.5} />
          {/* 太极 S 曲线 */}
          <path
            d="M 24,0 A 24,24 0 0,1 24,48 A 12,12 0 0,1 24,24 A 12,12 0 0,0 24,0 Z"
            fill="var(--color-gold)"
            fillOpacity={0.4}
          />
          {/* 阳眼 */}
          <circle cx={24} cy={12} r={3} fill="#0d1b26" />
          {/* 阴眼 */}
          <circle cx={24} cy={36} r={3} fill="var(--color-gold)" fillOpacity={0.85} />
        </g>
      </svg>
    </div>
  );
}

/**
 * 传统朱砂印章（SealStamp）
 * 模拟古籍典册红印，采用双框微圆角、朱砂深红渐变与宋体篆刻风格。
 */
export function SealStamp({
  text,
  size = 28,
  className = "",
}: {
  text: string;
  size?: number;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center justify-center rounded-[3px] select-none font-medium ${className}`}
      style={{
        width: size,
        height: size,
        background: "linear-gradient(145deg, #992d24 0%, #6e1c17 100%)",
        border: "1px solid #b34237",
        boxShadow: "inset 0 0 0 1.5px rgba(245, 215, 175, 0.28), 0 2px 6px rgba(0,0,0,0.35)",
        color: "#fbe8cf",
        fontFamily: "var(--font-serif-cn)",
        fontSize: Math.max(11, Math.round(size * 0.44)),
        letterSpacing: "0.04em",
        lineHeight: 1,
      }}
      aria-label={`印章：${text}`}
      data-testid="seal-stamp"
    >
      {text}
    </span>
  );
}

/**
 * 东方山水远黛剪影（MountainSilhouette）
 * 极低透明度水墨山峰，用于增强 Hero 背景深度。
 */
export function MountainSilhouette({
  className = "",
  opacity = 0.07,
}: {
  className?: string;
  opacity?: number;
}) {
  return (
    <div
      className={`absolute inset-x-0 bottom-0 pointer-events-none overflow-hidden select-none ${className}`}
      style={{ height: 110, opacity }}
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 1200 120"
        preserveAspectRatio="none"
        className="h-full w-full"
      >
        <defs>
          <linearGradient id="mountainGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#d4b87a" stopOpacity="0.6" />
            <stop offset="40%" stopColor="#7c9ab8" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#09141f" stopOpacity="0.05" />
          </linearGradient>
        </defs>
        {/* 远山层 */}
        <path
          d="M0,80 Q160,35 320,60 T640,40 T960,65 T1200,45 L1200,120 L0,120 Z"
          fill="url(#mountainGrad)"
          opacity={0.5}
        />
        {/* 近山层 */}
        <path
          d="M0,95 Q220,55 450,75 T880,50 T1200,80 L1200,120 L0,120 Z"
          fill="url(#mountainGrad)"
          opacity={0.8}
        />
      </svg>
    </div>
  );
}
