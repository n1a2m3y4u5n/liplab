// V2 렌더 하네스 빌드(앱 빌드와 별개). 앱 모듈은 @app(frontend/src), 얼굴은 @front(frontend)로 가져온다.
//   cd scripts/v2_render && ../../frontend/node_modules/.bin/vite build --config vite.config.mjs --outDir <밖의 폴더>

import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const front = path.resolve(here, '../../frontend')
export default ({
  root: here,
  base: './',
  publicDir: false,
  assetsInclude: ['**/*.glb'],
  resolve: {
    alias: {
      '@app': path.join(front, 'src'),
      '@front': front,
      three: path.join(front, 'node_modules/three'),
    },
  },
  server: { port: 5195, fs: { allow: [path.resolve(here, '../..'), path.resolve(front, 'node_modules')] } },
  build: { emptyOutDir: true, assetsInlineLimit: 0, target: 'es2020' },
})
