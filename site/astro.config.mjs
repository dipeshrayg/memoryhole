import { defineConfig } from 'astro/config';

// SITE_URL and BASE_PATH are set by the GitHub Actions workflow
// (https://<owner>.github.io and /<repo>/). Defaults suit local dev.
export default defineConfig({
  site: process.env.SITE_URL || 'http://localhost:4321',
  base: process.env.BASE_PATH || '/',
});
