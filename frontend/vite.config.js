import { defineConfig } from 'vite';

// En desarrollo (npm run dev) /api se redirige a la API local; en producción lo hace nginx.
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: (p) => p.replace(/^\/api/, ''),
        headers: { 'X-API-Key': process.env.API_KEY || 'dev' },
      },
    },
  },
});
