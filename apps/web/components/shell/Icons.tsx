/**
 * 内联 SVG 图标集。
 *
 * 不引入第三方图标库：参考图中的图标是线性风格，用内联 SVG 精确控制
 * 尺寸（16px 网格）与描边（1.5px），避免额外的运行时依赖。
 */

import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Base({ size = 16, children, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconHome = (p: IconProps) => (
  <Base {...p}>
    <path d="M3 10.5 12 3l9 7.5" />
    <path d="M5.5 9.5V20h13V9.5" />
    <path d="M9.5 20v-6h5v6" />
  </Base>
);

export const IconChart = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
  </Base>
);

export const IconCalendar = (p: IconProps) => (
  <Base {...p}>
    <rect x="3" y="5" width="18" height="16" rx="2" />
    <path d="M3 10h18M8 3v4M16 3v4" />
  </Base>
);

export const IconTaiji = (p: IconProps) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 3a4.5 4.5 0 0 0 0 9 4.5 4.5 0 0 1 0 9" />
    <circle cx="12" cy="7.5" r="1.1" fill="currentColor" stroke="none" />
    <circle cx="12" cy="16.5" r="1.1" fill="currentColor" stroke="none" />
  </Base>
);

export const IconStar4 = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2z" />
  </Base>
);

export const IconTrend = (p: IconProps) => (
  <Base {...p}>
    <path d="M3 17l5-5 4 3 5-7" />
    <path d="M14 8h4v4" />
  </Base>
);

export const IconBook = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H19v15H6.5A2.5 2.5 0 0 0 4 20.5z" />
    <path d="M8 7h7M8 10.5h5" />
  </Base>
);

export const IconNodes = (p: IconProps) => (
  <Base {...p}>
    <circle cx="6" cy="7" r="2.4" />
    <circle cx="18" cy="7" r="2.4" />
    <circle cx="12" cy="17" r="2.4" />
    <path d="M7.7 8.8 10.5 15M16.3 8.8 13.5 15M8.4 7h7.2" />
  </Base>
);

export const IconFlask = (p: IconProps) => (
  <Base {...p}>
    <path d="M9 3h6M10 3v6L5 19a1.6 1.6 0 0 0 1.4 2.4h11.2A1.6 1.6 0 0 0 19 19l-5-10V3" />
    <path d="M7.5 15h9" />
  </Base>
);

export const IconDatabase = (p: IconProps) => (
  <Base {...p}>
    <ellipse cx="12" cy="5.5" rx="7" ry="2.8" />
    <path d="M5 5.5v13c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-13" />
    <path d="M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8" />
  </Base>
);

export const IconFlame = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 21c3.3 0 6-2.5 6-5.8 0-4.2-4.2-6.4-4.9-11.2-2 1.6-3.3 3.7-3.3 5.6 0 1.4.7 2.3.7 3.1 0 .9-.7 1.5-1.5 1.5S7.5 13.6 7.5 12c0-.5.1-.9.2-1.3C6.7 12 6 13.5 6 15.2 6 18.4 8.7 21 12 21z" />
  </Base>
);

export const IconSettings = (p: IconProps) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6" />
  </Base>
);

export const IconSearch = (p: IconProps) => (
  <Base {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m16 16 4.5 4.5" />
  </Base>
);

export const IconArrowRight = (p: IconProps) => (
  <Base {...p}>
    <path d="M5 12h13M12.5 6.5 18.5 12l-6 5.5" />
  </Base>
);

export const IconArrowUp = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 19V5M6.5 10.5 12 5l5.5 5.5" />
  </Base>
);

export const IconArrowDown = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 5v14M17.5 13.5 12 19l-5.5-5.5" />
  </Base>
);

export const IconMinus = (p: IconProps) => (
  <Base {...p}>
    <path d="M6 12h12" />
  </Base>
);

export const IconCheck = (p: IconProps) => (
  <Base {...p}>
    <path d="M4.5 12.5 9.5 17.5 19.5 6.5" />
  </Base>
);

export const IconClose = (p: IconProps) => (
  <Base {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Base>
);

export const IconWarning = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 3.8 21 20H3z" />
    <path d="M12 10v4M12 17.2v.1" />
  </Base>
);

export const IconTarget = (p: IconProps) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4.2" />
    <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
  </Base>
);

export const IconGrid = (p: IconProps) => (
  <Base {...p}>
    <rect x="4" y="4" width="7" height="7" rx="1.4" />
    <rect x="13" y="4" width="7" height="7" rx="1.4" />
    <rect x="4" y="13" width="7" height="7" rx="1.4" />
    <rect x="13" y="13" width="7" height="7" rx="1.4" />
  </Base>
);

export const IconLayers = (p: IconProps) => (
  <Base {...p}>
    <path d="m12 3 8.5 4.6L12 12.2 3.5 7.6z" />
    <path d="m3.5 12.4 8.5 4.6 8.5-4.6" />
    <path d="m3.5 16.8 8.5 4.6 8.5-4.6" />
  </Base>
);

export const IconGauge = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 17a8 8 0 1 1 16 0" />
    <path d="m12 13 4-3.5" />
    <circle cx="12" cy="13.6" r="1.2" fill="currentColor" stroke="none" />
  </Base>
);

export const IconLing = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 2.5 14.4 9 21 11.4l-6.6 2.4L12 20.5l-2.4-6.7L3 11.4 9.6 9z" />
  </Base>
);

export const IconDiamond = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 3.2 20.8 12 12 20.8 3.2 12z" />
    <path d="M12 8.2 15.8 12 12 15.8 8.2 12z" />
  </Base>
);

export const IconScroll = (p: IconProps) => (
  <Base {...p}>
    <path d="M6 4h11a2 2 0 0 1 2 2v12a2 2 0 0 0 2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 0-2-2z" />
    <path d="M9 9h6M9 13h6" />
  </Base>
);

export const IconStar = (p: IconProps) => (
  <Base {...p}>
    <path d="m12 3.5 2.6 5.6 6.1.8-4.5 4.2 1.2 6-5.4-3-5.4 3 1.2-6L3.3 9.9l6.1-.8z" />
  </Base>
);

export const IconExport = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 15V4M8 7.5 12 3.5l4 4" />
    <path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15" />
  </Base>
);

export const IconRefresh = (p: IconProps) => (
  <Base {...p}>
    <path d="M20 12a8 8 0 1 1-2.6-5.9" />
    <path d="M20 4v4.5h-4.5" />
  </Base>
);

export const IconClock = (p: IconProps) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 1.8" />
  </Base>
);

export const IconSpark = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4" />
    <path d="M6.4 6.4 9 9M15 15l2.6 2.6M17.6 6.4 15 9M9 15l-2.6 2.6" />
  </Base>
);

export const IconLotus = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 20c-4.2 0-7.6-2.6-8.6-6.2 3 .3 5.6 1.6 7.3 3.6" />
    <path d="M12 20c4.2 0 7.6-2.6 8.6-6.2-3 .3-5.6 1.6-7.3 3.6" />
    <path d="M12 20c-1.6-2.7-2.4-6-2-9.4.8-2 1.6-3.6 2-5.6.4 2 1.2 3.6 2 5.6.4 3.4-.4 6.7-2 9.4z" />
  </Base>
);
