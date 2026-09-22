// Shared comic-reader behaviour for the design mockups.
// Each design owns its markup and styling; this file owns state and navigation:
//   - elements with data-nav="first|prev|random|next|last" navigate
//   - elements with data-view="comic|archive" switch views (body[data-view])
//   - ← / → (and h / l), Home / End, r = random, a = archive, Esc = back
//   - #82 in the URL opens comic 82 when a design is opened on its own
(function () {
  const data = window.HARDLY_FUNNY;
  const comics = data.comics;
  const ASSETS = "../archive/";
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];
  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  function parts(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return { y, m, d, date: new Date(Date.UTC(y, m - 1, d)) };
  }

  const format = {
    long: (iso) => { const p = parts(iso); return `${MONTHS_LONG[p.m - 1]} ${p.d}, ${p.y}`; },
    short: (iso) => { const p = parts(iso); return `${MONTHS[p.m - 1]} ${p.d}, ${p.y}`; },
    git: (iso) => { const p = parts(iso); return `${DAYS[p.date.getUTCDay()]} ${MONTHS[p.m - 1]} ${p.d} ${p.y}`; },
    sheet: (iso) => { const p = parts(iso); return `${String(p.m).padStart(2, "0")}/${String(p.d).padStart(2, "0")}/${p.y}`; },
    epoch: (iso) => String(parts(iso).date.getTime() / 1000),
  };

  // Stable, decorative 7-char "commit hash" per comic (FNV-1a over the slug).
  function shortHash(text) {
    let h = 0x811c9dc5;
    for (const ch of text) { h ^= ch.charCodeAt(0); h = Math.imul(h, 0x01000193) >>> 0; }
    return (h >>> 0).toString(16).padStart(8, "0").slice(0, 7);
  }

  function src(image) { return ASSETS + image.src; }

  function byYear() {
    const groups = new Map();
    comics.forEach((c, i) => {
      const y = c.date.slice(0, 4);
      if (!groups.has(y)) groups.set(y, []);
      groups.get(y).push({ comic: c, index: i });
    });
    return groups;
  }

  function reader({ render, renderArchive }) {
    let index = comics.length - 1;
    const fromHash = Number((location.hash || "").replace("#", ""));
    if (fromHash >= 1 && fromHash <= comics.length) index = fromHash - 1;

    function setView(view) {
      document.body.dataset.view = view;
      if (view === "archive") window.scrollTo({ top: 0 });
    }

    function syncNav() {
      document.querySelectorAll("[data-nav]").forEach((el) => {
        const kind = el.dataset.nav;
        const atStart = index === 0, atEnd = index === comics.length - 1;
        const off = ((kind === "first" || kind === "prev") && atStart) ||
                    ((kind === "next" || kind === "last") && atEnd);
        el.toggleAttribute("disabled", off);
        el.setAttribute("aria-disabled", String(off));
      });
    }

    function preload(i) {
      const c = comics[i];
      if (c) c.images.forEach((img) => { new Image().src = src(img); });
    }

    function go(i, { view = "comic" } = {}) {
      index = Math.max(0, Math.min(comics.length - 1, i));
      const comic = comics[index];
      render(comic, index);
      syncNav();
      setView(view);
      preload(index - 1);
      preload(index + 1);
      try { history.replaceState(null, "", "#" + comic.number); } catch (e) { /* srcdoc previews */ }
    }

    const actions = {
      first: () => go(0),
      prev: () => go(index - 1),
      next: () => go(index + 1),
      last: () => go(comics.length - 1),
      random: () => {
        let i = index;
        while (comics.length > 1 && i === index) i = Math.floor(Math.random() * comics.length);
        go(i);
      },
    };

    document.addEventListener("click", (e) => {
      const nav = e.target.closest("[data-nav]");
      if (nav) {
        e.preventDefault();
        if (nav.hasAttribute("disabled")) setView("comic");
        else actions[nav.dataset.nav]();
        return;
      }
      const view = e.target.closest("[data-view]");
      if (view) { e.preventDefault(); setView(view.dataset.view); return; }
      const pick = e.target.closest("[data-goto]");
      if (pick) { e.preventDefault(); go(Number(pick.dataset.goto)); window.scrollTo({ top: 0 }); }
    });

    document.addEventListener("keydown", (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey || /input|textarea|select/i.test(e.target.tagName)) return;
      const key = e.key;
      if (key === "ArrowLeft" || key === "h") actions.prev();
      else if (key === "ArrowRight" || key === "l") actions.next();
      else if (key === "Home") actions.first();
      else if (key === "End") actions.last();
      else if (key === "r") actions.random();
      else if (key === "a") setView("archive");
      else if (key === "Escape") setView("comic");
      else return;
      e.preventDefault();
    });

    if (renderArchive) renderArchive(comics);
    go(index);
    return { go, actions, get index() { return index; } };
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  window.HF = { data, comics, format, shortHash, src, byYear, reader, escapeHtml, assets: ASSETS };
})();
