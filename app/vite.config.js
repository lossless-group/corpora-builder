import { sveltekit } from '@sveltejs/kit/vite';
import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

// SvelteKit 3 takes its configuration here; `svelte.config.js` is no longer
// read, and its presence is a build error. The static adapter with an
// `index.html` fallback is what lets the Tauri webview load a file, not a server.
//
// `$lib` is kept as an explicit alias. Kit 3 dropped it in favour of `#lib`
// (package.json subpath imports), but this app's conventions are converged
// with memopop-native, which uses `$lib/` — copy-from only works while both
// spell imports the same way. Migrate both together, or neither.
export default {
  plugins: [
    sveltekit({
      preprocess: vitePreprocess(),
      adapter: adapter({ fallback: 'index.html' }),
      alias: { $lib: 'src/lib' }
    })
  ],
  clearScreen: false,
  server: { port: 1420, strictPort: true, watch: { ignored: ['**/src-tauri/**'] } }
};
