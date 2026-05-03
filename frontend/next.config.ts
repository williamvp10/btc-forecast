import type { NextConfig } from "next";

function normalizeBackendUrl(value?: string): string {
  return (value ?? "")
    .trim()
    .replace(/^['"`]+|['"`]+$/g, "")
    .replace(/\/+$/, "");
}

const nextConfig: NextConfig = {
  async rewrites() {
    const backendUrl =
      normalizeBackendUrl(process.env.BACKEND_URL) ||
      (process.env.NODE_ENV === "production" ? "http://backend:8000" : "http://localhost:8000");

    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/health/:path*",
        destination: `${backendUrl}/health/:path*`,
      },
    ];
  },
};

export default nextConfig;
