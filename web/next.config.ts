import type { NextConfig } from "next";

// The browser only ever talks to Next.js. Calls to /api/* are passed on to the
// workflow service, so there's one origin: the session cookie stays first-party
// and no CORS setup is needed.
// API_URL is read when the app is built, not when it starts: the rewrite is
// written into the build output.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  devIndicators: false,
  // Container builds set BUILD_STANDALONE=1 for a self-contained server.
  output: process.env.BUILD_STANDALONE ? "standalone" : undefined,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default config;
