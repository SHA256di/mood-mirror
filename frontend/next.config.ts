import type { NextConfig } from "next";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "https://querate-backend-862135384918.us-central1.run.app";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${BACKEND}/:path*`,
      },
    ];
  },
};

export default nextConfig;
