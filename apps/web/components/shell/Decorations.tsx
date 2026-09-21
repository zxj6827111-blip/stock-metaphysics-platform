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
      className={`flex items-center justify-center select-none pointer-events-none ${className.includes("absolute") ? "" : "relative"} ${className}`}
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
          const round = (n: number) => Math.round(n * 100) / 100;
          const x1 = round(center + r1 * Math.cos(rad));
          const y1 = round(center + r1 * Math.sin(rad));
          const x2 = round(center + r2 * Math.cos(rad));
          const y2 = round(center + r2 * Math.sin(rad));
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

        {/* 八卦与十二地支外环 */}
        <circle
          cx={center}
          cy={center}
          r={105}
          fill="none"
          stroke="url(#goldLine)"
          strokeOpacity={0.65}
          strokeWidth={1}
        />
        {branches.map((b, i) => {
          // 子在正上方 (270度 = -90度)
          const angle = (i * 360) / 12 - 90;
          const rad = (angle * Math.PI) / 180;
          const r = 114;
          const round = (n: number) => Math.round(n * 100) / 100;
          const x = round(center + r * Math.cos(rad));
          const y = round(center + r * Math.sin(rad));
          return (
            <text
              key={b}
              x={x}
              y={y + 3.5}
              textAnchor="middle"
              fill="var(--color-gold-strong)"
              fillOpacity={0.88}
              fontSize={10.5}
              fontFamily="var(--font-serif-cn)"
              style={{ fontWeight: 600 }}
            >
              {b}
            </text>
          );
        })}

        {/* 八卦微印记 */}
        {["乾", "坎", "艮", "震", "巽", "离", "坤", "兑"].map((g, i) => {
          const angle = (i * 360) / 8 - 90;
          const rad = (angle * Math.PI) / 180;
          const r = 96;
          const round = (n: number) => Math.round(n * 100) / 100;
          const x = round(center + r * Math.cos(rad));
          const y = round(center + r * Math.sin(rad));
          return (
            <text
              key={g}
              x={x}
              y={y + 3}
              textAnchor="middle"
              fill="var(--color-gold)"
              fillOpacity={0.5}
              fontSize={9}
              fontFamily="var(--font-serif-cn)"
            >
              {g}
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
          strokeWidth={1.2}
          strokeOpacity={0.55}
        />
        <circle
          cx={center}
          cy={center}
          r={62}
          fill="none"
          stroke="var(--color-gold)"
          strokeWidth={0.9}
          strokeDasharray="3 3"
          strokeOpacity={0.45}
        />

        {/* 星轨天体圆点 */}
        {[-35, 45, 130, 220].map((deg, i) => {
          const rad = (deg * Math.PI) / 180;
          const r = i % 2 === 0 ? 86 : 62;
          const round = (n: number) => Math.round(n * 100) / 100;
          const cx = round(center + r * Math.cos(rad));
          const cy = round(center + r * Math.sin(rad));
          return (
            <circle
              key={deg}
              cx={cx}
              cy={cy}
              r={i % 2 === 0 ? 3 : 2.2}
              fill="var(--color-gold-strong)"
              fillOpacity={0.9}
              filter="drop-shadow(0 0 4px rgba(212,184,122,0.8))"
            />
          );
        })}

        {/* 核心太极阴阳盘 */}
        <g transform={`translate(${center - 24}, ${center - 24})`}>
          <circle cx={24} cy={24} r={24} fill="#0d1b26" stroke="var(--color-gold)" strokeWidth={1.5} strokeOpacity={0.8} />
          {/* 太极 S 曲线 */}
          <path
            d="M 24,0 A 24,24 0 0,1 24,48 A 12,12 0 0,1 24,24 A 12,12 0 0,0 24,0 Z"
            fill="var(--color-gold)"
            fillOpacity={0.7}
          />
          {/* 阳眼 */}
          <circle cx={24} cy={12} r={3.2} fill="#0d1b26" />
          {/* 阴眼 */}
          <circle cx={24} cy={36} r={3.2} fill="var(--color-gold-strong)" fillOpacity={0.95} />
        </g>

        {/* 四维天地人方位标记 */}
        <text
          x={center}
          y={center - 35}
          textAnchor="middle"
          fill="var(--color-gold-strong)"
          fillOpacity={0.95}
          fontSize={14}
          fontFamily="var(--font-serif-cn)"
          style={{ fontWeight: 700, textShadow: "0 0 10px rgba(212,184,122,0.5)" }}
        >
          天
        </text>
        <text
          x={center}
          y={center + 46}
          textAnchor="middle"
          fill="var(--color-gold-strong)"
          fillOpacity={0.95}
          fontSize={14}
          fontFamily="var(--font-serif-cn)"
          style={{ fontWeight: 700, textShadow: "0 0 10px rgba(212,184,122,0.5)" }}
        >
          人
        </text>
        <text
          x={center - 43}
          y={center + 5}
          textAnchor="middle"
          fill="var(--color-gold-strong)"
          fillOpacity={0.95}
          fontSize={14}
          fontFamily="var(--font-serif-cn)"
          style={{ fontWeight: 700, textShadow: "0 0 10px rgba(212,184,122,0.5)" }}
        >
          地
        </text>
        <text
          x={center + 43}
          y={center + 5}
          textAnchor="middle"
          fill="var(--color-gold-strong)"
          fillOpacity={0.95}
          fontSize={14}
          fontFamily="var(--font-serif-cn)"
          style={{ fontWeight: 700, textShadow: "0 0 10px rgba(212,184,122,0.5)" }}
        >
          地
        </text>
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
        background: "linear-gradient(145deg, #9e2a22 0%, #681712 100%)",
        border: "1px solid #bf3e32",
        boxShadow: "inset 0 0 0 1.2px rgba(245, 215, 175, 0.35), 0 2px 8px rgba(0,0,0,0.45)",
        color: "#fbe8cf",
        fontFamily: "var(--font-serif-cn)",
        fontSize: Math.max(10, Math.round(size * 0.46)),
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
 * 东方水墨连绵远山（MountainSilhouette）
 * 多层重山叠嶂、层峦耸翠、晨雾金辉水墨画卷。
 */
export function MountainSilhouette({
  className = "",
  opacity = 0.28,
}: {
  className?: string;
  opacity?: number;
}) {
  return (
    <div
      className={`absolute inset-x-0 bottom-0 pointer-events-none overflow-hidden select-none ${className}`}
      style={{ height: 160, opacity }}
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 1600 180"
        preserveAspectRatio="none"
        className="h-full w-full"
      >
        <defs>
          {/* 远山渐变：青黛墨色 */}
          <linearGradient id="farMountain" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#41576d" stopOpacity="0.75" />
            <stop offset="50%" stopColor="#233547" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#0c1722" stopOpacity="0.05" />
          </linearGradient>
          {/* 中景山峰渐变：深邃墨崖与微金微曦 */}
          <linearGradient id="midMountain" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#7a6742" stopOpacity="0.65" />
            <stop offset="35%" stopColor="#293949" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#0a1520" stopOpacity="0.1" />
          </linearGradient>
          {/* 近景峭壁：浓墨重彩 */}
          <linearGradient id="nearMountain" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#1a2b3a" stopOpacity="0.9" />
            <stop offset="60%" stopColor="#101c27" stopOpacity="0.95" />
            <stop offset="100%" stopColor="#081018" stopOpacity="0.2" />
          </linearGradient>
          {/* 晨曦云雾遮罩 */}
          <linearGradient id="mistGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#d4b87a" stopOpacity="0.15" />
            <stop offset="40%" stopColor="#1e3447" stopOpacity="0.2" />
            <stop offset="100%" stopColor="#09141f" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* 远山重峦层 (Layer 1) */}
        <path
          d="M0,110 Q120,45 260,75 T540,50 T820,80 T1100,40 T1380,65 Q1500,45 1600,70 L1600,180 L0,180 Z"
          fill="url(#farMountain)"
        />
        {/* 中景奇峰险壑 (Layer 2) */}
        <path
          d="M0,135 Q180,65 380,105 T760,70 T1160,95 T1450,55 Q1540,75 1600,100 L1600,180 L0,180 Z"
          fill="url(#midMountain)"
        />
        {/* 峦间云雾缭绕带 (Mist) */}
        <path
          d="M0,145 Q250,110 500,135 T1000,115 T1600,130 L1600,180 L0,180 Z"
          fill="url(#mistGrad)"
        />
        {/* 近景浓墨叠障 (Layer 3) */}
        <path
          d="M0,150 Q140,110 320,135 T720,110 T1120,130 T1520,95 L1600,120 L1600,180 L0,180 Z"
          fill="url(#nearMountain)"
        />
      </svg>
    </div>
  );
}

/**
 * 侧栏底部小幅山水插画
 */
export function SidebarMountain() {
  return (
    <div className="w-full h-[40px] pointer-events-none select-none overflow-hidden opacity-35" aria-hidden="true">
      <svg viewBox="0 0 200 40" preserveAspectRatio="none" className="w-full h-full">
        <path
          d="M0,35 Q30,12 65,24 T130,15 T200,28 L200,40 L0,40 Z"
          fill="url(#sbMountain)"
        />
        <defs>
          <linearGradient id="sbMountain" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#d4b87a" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#1a2d3d" stopOpacity="0.1" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  );
}
