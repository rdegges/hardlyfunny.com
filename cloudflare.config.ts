import { defineConfig } from "cf/config";

export default defineConfig({
  worker: {
    name: "hardlyfunny",
    compatibilityDate: "2026-10-01",
    assets: {
      // Comic pages live at /comics/<slug>/index.html, and the build writes a 404.html.
      htmlHandling: "auto-trailing-slash",
      notFoundHandling: "404-page",
    },
  },
});
