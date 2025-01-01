import type { NextConfig } from "next";

module.exports = {
  env: {
    NEXT_PUBLIC_BACKEND_API_URL: process.env.NEXT_PUBLIC_BACKEND_API_URL,
  },
};

const nextConfig: NextConfig = {
  /* config options here */
};

export default nextConfig;
