import base from './vite.config.ts';
import { defineConfig } from 'vite';

// Type checking is run separately; native minification avoids concurrent Terser
// workers exhausting memory on small development machines.
export default defineConfig(async env => {
    const config = typeof base === 'function' ? await base(env) : await base;
    config.plugins = config.plugins?.filter(plugin => !(plugin && !Array.isArray(plugin) && 'name' in plugin && plugin.name === 'vite-plugin-checker'));
    config.build = { ...config.build, minify: 'oxc' };
    return config;
});
