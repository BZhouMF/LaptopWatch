const config = {
  plugins: {
    "@tailwindcss/postcss": {},
    // Polyfills for older browsers (e.g. Baidu Browser):
    // 1. Convert oklch() colors to rgb() — Chrome 111+
    "@csstools/postcss-oklab-function": { preserve: false },
    // 2. Convert color-mix() to static colors — Chrome 111+
    "@csstools/postcss-color-mix-function": { preserve: false },
    // 3. Flatten @layer blocks — Chrome 99+
    "@csstools/postcss-cascade-layers": {},
  },
};

export default config;
