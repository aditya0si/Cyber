/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // `output: "standalone"` is needed for the prod Docker image (Dockerfile.web).
  // On Windows it triggers EPERR-symlink during .next/standalone packaging;
  // pnpm-hoisted dev builds on win32 skip it; CI (Linux) & Docker still use it.
  output: process.platform === "win32" ? undefined : "standalone",
  async rewrites() {
    const api = process.env.API_ORIGIN ?? "http://localhost:8000";
    return [
      { source: "/v1/:path*", destination: `${api}/v1/:path*` },
    ];
  },
};

export default nextConfig;
