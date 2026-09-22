// Hardly Funny: progressive enhancement only. Every page works without this file.
//  - the Samantha / Randall switch (and relabelling in Randall mode)
//  - single-key shortcuts, which readers can turn off (WCAG 2.1.4)
//  - Instagram sharing via the native share sheet, and copy-link
(function () {
  "use strict";
  var root = document.documentElement;
  var dark = window.matchMedia("(prefers-color-scheme: dark)");

  function store(key, value) {
    try { value === undefined ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch (e) { /* private mode */ }
  }
  function read(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  // ---- Samantha / Randall mode -------------------------------------------
  function mode() {
    return root.dataset.mode || (dark.matches ? "randall" : "samantha");
  }

  // Elements carry their Randall-mode text in data-r. Their normal text stays in the
  // HTML (so search engines and screen readers get plain words), and data-label keeps
  // the plain meaning in the accessible name when the jargon is showing.
  var relabelled = Array.prototype.slice.call(document.querySelectorAll("[data-r]"));
  relabelled.forEach(function (el) { el.dataset.s = el.textContent; });

  function applyMode() {
    var randall = mode() === "randall";
    relabelled.forEach(function (el) {
      el.textContent = randall ? el.dataset.r : el.dataset.s;
      if (el.dataset.label) {
        if (randall) el.setAttribute("aria-label", el.dataset.r + " (" + el.dataset.label + ")");
        else el.removeAttribute("aria-label");
      }
    });
    var toggle = document.getElementById("mode");
    if (toggle) toggle.setAttribute("aria-checked", String(randall));
    var s = document.getElementById("lbl-s"), r = document.getElementById("lbl-r");
    if (s && r) { s.classList.toggle("on", !randall); r.classList.toggle("on", randall); }
  }

  function toggleMode() {
    root.dataset.mode = mode() === "randall" ? "samantha" : "randall";
    store("hf-mode", root.dataset.mode);
    applyMode();
  }

  var modeButton = document.getElementById("mode");
  if (modeButton) modeButton.addEventListener("click", toggleMode);
  if (dark.addEventListener) dark.addEventListener("change", applyMode);
  applyMode();

  // ---- Keyboard shortcuts --------------------------------------------------
  var keysOn = read("hf-keys") !== "off";
  var keysToggle = document.getElementById("keys-toggle");
  function renderKeysToggle() {
    if (!keysToggle) return;
    keysToggle.setAttribute("aria-pressed", String(keysOn));
    keysToggle.textContent = keysOn ? "Shortcuts on" : "Shortcuts off";
  }
  if (keysToggle) keysToggle.addEventListener("click", function () {
    keysOn = !keysOn;
    store("hf-keys", keysOn ? undefined : "off");
    renderKeysToggle();
  });
  renderKeysToggle();

  var pages = { a: "/archive/", i: "/about/" };
  document.addEventListener("keydown", function (e) {
    if (!keysOn || e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
    var t = e.target;
    if (t.isContentEditable || /^(input|textarea|select)$/i.test(t.tagName)) return;
    if (e.key === "m") { toggleMode(); return; }
    var link = document.querySelector('a[data-key="' + e.key + '"]');
    var href = link ? link.getAttribute("href") : pages[e.key];
    if (e.key === "r" && !link) href = "/random/";
    if (href) { e.preventDefault(); location.href = href; }
  });

  // ---- Sharing -------------------------------------------------------------
  var status = document.querySelector(".share-status");
  function say(message) { if (status) status.textContent = message; }

  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text);
    return Promise.reject(new Error("no clipboard"));
  }

  document.addEventListener("click", function (e) {
    var copyButton = e.target.closest("[data-copy-link]");
    if (copyButton) {
      copy(copyButton.dataset.copyLink).then(
        function () { say("Link copied."); },
        function () { say("Couldn't copy automatically. The link is " + copyButton.dataset.copyLink); }
      );
      return;
    }

    // Instagram has no web share link, so hand the comic image to the device's share
    // sheet (which includes Instagram on phones). Elsewhere, copy the link and point
    // at the image so it can be saved and posted.
    var insta = e.target.closest("[data-share-instagram]");
    if (!insta) return;
    var url = insta.dataset.url, title = insta.dataset.title, image = insta.dataset.image;
    fetch(image)
      .then(function (res) { return res.blob(); })
      .then(function (blob) {
        var file = new File([blob], image.split("/").pop(), { type: blob.type || "image/png" });
        if (navigator.canShare && navigator.canShare({ files: [file] })) {
          return navigator.share({ files: [file], title: title, text: title + " " + url });
        }
        throw new Error("file sharing unsupported");
      })
      .catch(function (err) {
        if (err && err.name === "AbortError") return; // they closed the share sheet
        copy(url).catch(function () {});
        say("Instagram can only share from its app. We copied the link. Save the comic image (" +
          location.origin + image + ") and post it from Instagram.");
      });
  });
})();
