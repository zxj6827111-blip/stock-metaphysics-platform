/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 允许在离线/受限网络下构建
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: false },
  async rewrites() {
    // 前端直连后端 API，避免 CORS 配置分散在两处
    const apiBase = process.env.SMP_API_BASE || "http://127.0.0.1:8000";
    return [{ source: "/api/backend/:path*", destination: `${apiBase}/:path*` }];
  },
};

export default nextConfig;
