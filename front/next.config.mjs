/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  experimental: {
    serverActions: {
      // Detras de Cloudflare el header Host no coincide con el origen real y
      // Next rechaza las Server Actions por su chequeo de CSRF.
      allowedOrigins: ["inmobi-db.com", "www.inmobi-db.com"],
    },
  },
}

export default nextConfig
