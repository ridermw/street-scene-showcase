import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  publicDir: false,
  build: {
    target: 'esnext',
    outDir: 'docs/interactive/assets',
    emptyOutDir: true,
    sourcemap: false,
    lib: {
      entry: 'web/main.js',
      formats: ['es'],
      fileName: () => 'viewer.js',
      cssFileName: 'viewer',
    },
  },
});
