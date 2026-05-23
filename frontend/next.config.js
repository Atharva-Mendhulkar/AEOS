/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: "http://localhost:8000/api/v1/:path*",
      },
      {
        source: "/ws/events/:path*",
        destination: "http://localhost:8040/ws/events/:path*",
      },
      {
        source: "/socket.io/:path*",
        destination: "http://localhost:8040/socket.io/:path*",
      }
    ];
  },
};

module.exports = nextConfig;
