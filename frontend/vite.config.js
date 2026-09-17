import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        // three는 수동 청크로 지정하지 않는다(핵심). three-vendor 수동청크는 Rollup이
        // 공유 헬퍼(__vitePreload)·zustand를 그 무거운 청크로 호이스팅해, 엔트리가 three를
        // 정적 import → 초기 로드에서 three(~320KB)를 받게 만들었다(리뷰에서 확인).
        // three/@react-three는 오직 lazy 3D 페이지만 참조하므로 Rollup 자동 async 분리에
        // 맡겨 초기 진입에서 빠지게 한다. react/framer만 캐시 가능한 벤더 청크로 분리해
        // 엔트리(index)를 가볍게 유지한다. (검증: scratchpad/verify_firstpaint.py)
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'animation-vendor': ['framer-motion'],
        }
      }
    }
  }
})
