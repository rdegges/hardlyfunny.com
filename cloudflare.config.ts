import { defineConfig } from "cf/config";

export default defineConfig({
  worker: {
    name: "hardlyfunny",
    // Every deploy re-asserts the apex. Removing this line does not detach it; only the
    // dashboard does (see README "Domains"). www is a zone redirect rule, not a domain here.
    domains: ["hardlyfunny.com"],
    // Only hardlyfunny.com serves the site: no duplicate copy on workers.dev or on preview URLs.
    workersDev: false,
    previewUrls: false,
    compatibilityDate: "2026-10-01",
    assets: {
      // Comic pages live at /comics/<slug>/index.html, and the build writes a 404.html.
      htmlHandling: "auto-trailing-slash",
      notFoundHandling: "404-page",
    },
  },
});
