import path from "path";
import { fileURLToPath } from "url";

const root = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: root,
  // CI can set a separate directory so a production build does not corrupt
  // a developer's running `.next` cache.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
