/** @type {import('tailwindcss').Config} */
const feldspar = require("../feldspar/tailwind.config.js");

module.exports = {
  presets: [feldspar],
  content: ["./index.html", "./src/**/*.ts"],
  // The feldspar preset targets Tailwind 4 syntax in places; anything it
  // defines that Tailwind 3 rejects is overridden here rather than edited there.
  corePlugins: { gap: false },   // Safari 12 has no flex gap; use margins
};
