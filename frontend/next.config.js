/** Browser talks only to this Next server; /api/* is proxied to the Python backend (no secrets in the browser). */
module.exports = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/api/:path*` }];
  },
};
