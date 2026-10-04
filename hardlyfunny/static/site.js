// Hardly Funny: progressive enhancement only. Every page works without this file.
//  - the Samantha / Randall switch (and relabelling in Randall mode)
//  - single-key shortcuts, which readers can turn off (WCAG 2.1.4)
//  - Instagram sharing via the native share sheet, and copy-link
(function () {
  "use strict";
  var root = document.documentElement;
  var dark = window.matchMedia("(prefers-color-scheme: dark)");
  var MODES = { samantha: true, randall: true };

  function store(key, value) {
    try { value === undefined ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch (e) { /* private mode */ }
  }
  function read(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  // ---- Samantha / Randall mode -------------------------------------------
  if (root.dataset.mode && !MODES[root.dataset.mode]) delete root.dataset.mode;

  function mode() {
    return root.dataset.mode || (dark.matches ? "randall" : "samantha");
  }

  // Elements carry their Randall-mode text in data-r; the HTML itself only ever holds
  // the plain words. In Randall mode the jargon is shown, but assistive tech keeps the
  // plain meaning: links and buttons announce "jargon (plain)" so voice control can
  // still match the visible label; everything else announces only the plain text.
  var relabelled = Array.prototype.slice.call(document.querySelectorAll("[data-r]"));
  relabelled.forEach(function (el) { el.dataset.s = el.textContent.trim(); });

  function span(text, attrs) {
    var s = document.createElement("span");
    s.textContent = text;
    for (var k in attrs) s.setAttribute(k, attrs[k]);
    return s;
  }

  function relabel(el, randall) {
    var plain = el.dataset.label || el.dataset.s;
    el.textContent = "";
    if (!randall) { el.textContent = el.dataset.s; return; }
    var interactive = /^(A|BUTTON)$/.test(el.tagName);
    if (interactive) {
      el.appendChild(span(el.dataset.r));
      el.appendChild(span(" (" + plain + ")", { "class": "visually-hidden" }));
    } else {
      el.appendChild(span(el.dataset.r, { "aria-hidden": "true" }));
      el.appendChild(span(plain, { "class": "visually-hidden" }));
    }
  }

  var themeColor = document.querySelectorAll('meta[name="theme-color"]');

  function applyMode() {
    var randall = mode() === "randall";
    relabelled.forEach(function (el) { relabel(el, randall); });
    var toggle = document.getElementById("mode");
    if (toggle) toggle.setAttribute("aria-checked", String(randall));
    var s = document.getElementById("lbl-s"), r = document.getElementById("lbl-r");
    if (s && r) { s.classList.toggle("on", !randall); r.classList.toggle("on", randall); }
    // Browser chrome follows the switch, not just the OS setting.
    for (var i = 0; i < themeColor.length; i++) {
      themeColor[i].setAttribute("content", randall ? "#19191b" : "#fff4fa");
      themeColor[i].removeAttribute("media");
    }
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
  var keysState = document.getElementById("keys-state");
  function renderKeysToggle() {
    if (!keysToggle) return;
    keysToggle.setAttribute("aria-pressed", String(keysOn));
    if (keysState) keysState.textContent = keysOn ? "on" : "off";
  }
  if (keysToggle) keysToggle.addEventListener("click", function () {
    keysOn = !keysOn;
    store("hf-keys", keysOn ? undefined : "off");
    renderKeysToggle();
  });
  renderKeysToggle();

  var shortcutLinks = {};
  Array.prototype.forEach.call(document.querySelectorAll("a[data-key]"), function (a) {
    if (!shortcutLinks[a.dataset.key]) shortcutLinks[a.dataset.key] = a;
  });

  document.addEventListener("keydown", function (e) {
    if (!keysOn || e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || e.shiftKey || e.isComposing) return;
    var t = e.target;
    if (t.isContentEditable || /^(input|textarea|select)$/i.test(t.tagName)) return;
    // Arrows stay with focused controls (e.g. an open transcript) and horizontal scrolling.
    if (/^Arrow/.test(e.key) && t !== document.body && t.id !== "main") return;
    if (e.key === "m") { e.preventDefault(); toggleMode(); return; }
    var link = shortcutLinks[e.key];
    if (link) { e.preventDefault(); location.href = link.href; }
  });

  // ---- 404: three random comics instead of the fixed favourites ------------
  var pool = Array.prototype.slice.call(document.querySelectorAll("#lost-picks [data-pick]"));
  if (pool.length >= 3) {
    for (var i = pool.length - 1; i > 0; i--) {  // Fisher-Yates shuffle
      var j = Math.floor(Math.random() * (i + 1)), tmp = pool[i]; pool[i] = pool[j]; pool[j] = tmp;
    }
    Array.prototype.forEach.call(document.querySelectorAll("#lost-picks [data-default-pick]"), function (li) { li.hidden = true; });
    pool.slice(0, 3).forEach(function (li) {
      li.hidden = false;
      // The pool's thumbnails are lazy so a 404 doesn't fetch all of them; the three shown sit near the top.
      Array.prototype.forEach.call(li.querySelectorAll("img"), function (img) { img.loading = "eager"; });
    });
  }

  // ---- Sharing -------------------------------------------------------------
  var status = document.querySelector(".share-status");
  function say(message) { if (status) status.textContent = message; }

  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text);
    return Promise.reject(new Error("no clipboard"));
  }

  document.addEventListener("click", function (e) {
    var copyButton = e.target.closest("[data-copy-link]");
    if (!copyButton) return;
    var link = copyButton.dataset.copyLink;
    copy(link).then(
      function () { say("Link copied."); },
      function () { say("Couldn't copy automatically. The link is " + link); }
    );
  });

  // Instagram has no web share link, so hand the comic image to the device's share
  // sheet (which includes Instagram on phones). The image is fetched ahead of the tap,
  // because browsers only allow share() straight from the tap itself.
  var insta = document.querySelector("[data-share-instagram]");
  if (insta) {
    var imageFile = null, sharing = false;
    var imageUrl = new URL(insta.dataset.image, location.href).href;
    var prefetch = function () {
      if (imageFile || !window.fetch || !window.File) return;
      fetch(imageUrl).then(function (res) { return res.blob(); }).then(function (blob) {
        imageFile = new File([blob], imageUrl.split("/").pop(), { type: blob.type || "image/png" });
      }).catch(function () {});
    };
    insta.addEventListener("pointerenter", prefetch);
    insta.addEventListener("focus", prefetch);
    insta.addEventListener("touchstart", prefetch, { passive: true });
    if ("requestIdleCallback" in window) requestIdleCallback(prefetch); else setTimeout(prefetch, 2000);

    var fallback = function () {
      copy(insta.dataset.url).then(
        function () { say("Instagram only shares from its app. The link is copied; save the comic image (" + imageUrl + ") and post it from Instagram."); },
        function () { say("Instagram only shares from its app. Save the comic image (" + imageUrl + ") and post it from Instagram with this link: " + insta.dataset.url); }
      );
    };

    insta.addEventListener("click", function () {
      if (sharing) return;
      var data = { files: imageFile ? [imageFile] : [], title: insta.dataset.title, text: insta.dataset.title + " " + insta.dataset.url };
      if (!imageFile || !navigator.canShare || !navigator.canShare({ files: data.files })) { fallback(); return; }
      sharing = true;
      navigator.share(data).catch(function (err) {
        if (err && err.name !== "AbortError") fallback(); // AbortError: they closed the share sheet
      }).then(function () { sharing = false; });
    });
  }
})();
