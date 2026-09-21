/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 允许在离线/受限网络下构建
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: false },
  /**
   * 构建输出目录可覆盖。
   *
   * 为什么需要：`next dev` 与 `next start` 共用 `.next`，在同一工作目录里
   * 同时跑开发服务与生产验收时，`next build` 会摧毁 dev 的产物，dev 也会
   * 覆盖 start 需要的产物。验收实例用独立目录（如 `.next-e2e`）即可并存。
   */
  distDir: process.env.NEXT_DIST_DIR || ".next",
  async rewrites() {
    // 前端直连后端 API，避免 CORS 配置分散在两处
    const apiBase = process.env.SMP_API_BASE || "http://127.0.0.1:8000";
    return [{ source: "/api/backend/:path*", destination: `${apiBase}/:path*` }];
  },
};

export default nextConfig;
