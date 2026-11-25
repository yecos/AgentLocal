import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: __dirname,
  turbopack: { root: __dirname },
  reactStrictMode: false,
};

export default nextConfig;
