import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteSingleFile } from 'vite-plugin-singlefile'

// vite config docs if you need 'em
export default defineConfig({
  base: './',
  plugins: [vue(), viteSingleFile()],
})
