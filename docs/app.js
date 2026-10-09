// Randy Weston centennial page. Renders docs/data.json (built by
// site/build_site_data.py) into the static markup in index.html.
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'style') n.style.cssText = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat()) if (kid != null) n.append(kid);
    return n;
  };
  const svg = (tag, attrs, ...kids) => {
    const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) n.setAttribute(k, v);
    for (const kid of kids.flat()) if (kid != null) n.append(kid);
    return n;
  };
  const ext = (attrs) => Object.assign({ target: '_blank', rel: 'noopener' }, attrs);
  // a quote that already opens or closes with a mark keeps it rather than doubling it
  const q = (s) => (s.startsWith('“') ? '' : '“') + s + (s.endsWith('”') ? '' : '”');
  const initials = (name) => name.replace(/\(.*?\)/g, '').split(/\s+/).filter(Boolean).map((w) => w[0]).join('').slice(0, 3).toUpperCase();
  const avatar = (p) => el('span', { class: 'lj-avatar', 'aria-hidden': 'true' },
    p.img ? el('img', { src: p.img, alt: '', loading: 'lazy' }) : initials(p.name));
  // the build stamps a hash of the data into the page so a stale cached copy is never used
  const BUILD = (document.querySelector('meta[name="build"]') || {}).content || '';
  const versioned = (url) => (BUILD ? `${url}?v=${BUILD}` : url);
  const OWN = 'Randy Weston';
  let SOURCE = '';

  // ---------------------------------------------------------------- transcript passages
  // Every quote on the page opens here: the turns around it, read in place, with
  // a link to the archive's own copy. transcripts.json is fetched on first use.
  let transcripts = null;
  const loadTranscripts = () => transcripts || (transcripts = fetch(versioned('transcripts.json')).then((r) => {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }));
  const PAD = 6, STEP = 10;

  function marked(text, marks) {
    // wrap each quoted phrase found in this turn
    const spans = marks.filter(Boolean).map((m) => [text.indexOf(m), m.length])
      .filter(([at]) => at !== -1).sort((a, b) => a[0] - b[0]);
    const out = [];
    let pos = 0;
    for (const [at, len] of spans) {
      if (at < pos) continue;
      out.push(text.slice(pos, at), el('mark', null, text.slice(at, at + len)));
      pos = at + len;
    }
    out.push(text.slice(pos));
    return out;
  }

  function openPassage(ref) {
    const dlg = $('passage'), body = $('passage-body');
    $('passage-archive').textContent = '';
    $('passage-title').textContent = 'Loading…';
    $('passage-source').textContent = '';
    body.replaceChildren();
    if (!dlg.open) dlg.showModal();
    document.documentElement.style.overflow = 'hidden';

    loadTranscripts().then((all) => {
      const doc = all[ref.doc], blocks = doc.blocks;
      const targets = new Set(ref.blocks);
      const hits = blocks.map((b, i) => (targets.has(b.i) ? i : -1)).filter((i) => i !== -1);
      const first = hits.length ? hits[0] : 0;
      const last = hits.filter((i) => i - first <= 20).pop() ?? first;
      let lo = doc.complete ? Math.max(0, first - PAD) : 0;
      let hi = doc.complete ? Math.min(blocks.length, last + PAD + 1) : blocks.length;

      const page = blocks[first].p + 1;
      $('passage-archive').textContent = doc.archive;
      $('passage-title').textContent = doc.title;
      const src = $('passage-source');
      src.href = doc.url + (doc.pdf ? `#page=${page}` : '');
      src.textContent = `Original transcript at ${doc.at}` + (doc.pdf ? ` (PDF, page ${page})` : '');

      const row = (b, prev) => el('div', { class: 'turn' + (targets.has(b.i) ? ' target' : '') + (b.n ? ' note' : ''), 'data-i': b.i },
        (b.s || !prev || prev.p !== b.p) ? el('div', { class: 'turn-who' }, el('span', null, b.s),
          (!prev || prev.p !== b.p) ? el('span', { class: 'pg' }, `page ${b.p + 1}`) : null) : null,
        el('p', null, targets.has(b.i) ? marked(b.t, ref.marks || []) : b.t));

      const draw = (keep) => {
        const anchor = keep && body.querySelector(`[data-i="${keep}"]`);
        const before = anchor ? anchor.getBoundingClientRect().top : 0;
        const kids = [];
        if (lo > 0) kids.push(el('button', { type: 'button', class: 'lj-btn lj-btn-sm passage-more', onclick: () => { const k = blocks[lo].i; lo = Math.max(0, lo - STEP); draw(k); } }, 'Earlier'));
        else if (doc.complete) kids.push(el('div', { class: 'passage-edge' }, 'Start of the transcript'));
        for (let i = lo; i < hi; i++) kids.push(row(blocks[i], i > lo ? blocks[i - 1] : null));
        if (hi < blocks.length) kids.push(el('button', { type: 'button', class: 'lj-btn lj-btn-sm passage-more', onclick: () => { const k = blocks[hi - 1].i; hi = Math.min(blocks.length, hi + STEP); draw(k); } }, 'Later'));
        else if (doc.complete) kids.push(el('div', { class: 'passage-edge' }, 'End of the transcript'));
        else kids.push(el('div', { class: 'passage-edge' }, 'The interview continues in the original transcript'));
        body.replaceChildren(...kids);
        if (keep) {
          const now = body.querySelector(`[data-i="${keep}"]`);
          if (now) body.scrollTop += now.getBoundingClientRect().top - before;
        } else {
          const t = body.querySelector('.turn.target');
          if (t) body.scrollTop = t.offsetTop - body.offsetTop - Math.max(40, (body.clientHeight - t.offsetHeight) / 3);
        }
      };
      draw(null);
    }).catch((e) => { $('passage-title').textContent = `The transcript could not be loaded (${e.message}).`; });
  }

  function initPassage() {
    const dlg = $('passage');
    $('passage-close').addEventListener('click', () => dlg.close());
    dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });   // the backdrop
    dlg.addEventListener('close', () => { document.documentElement.style.overflow = ''; });
  }
  const readIt = (ref, label) => el('button', { type: 'button', class: 'linkish', onclick: () => openPassage(ref) }, label || 'Read the passage');
  const ownRef = (x) => ({ doc: 'own', blocks: x.b, marks: x.marks });

  // ---------------------------------------------------------------- lists that open out
  // Each list shows its best few first (the reader's grade, in the list's own
  // order) and opens to the whole list in that order. `reveal(id)` opens it as
  // far as one item, for the search box and the network.
  const lists = {};
  function expandable(key, items, first, host, btn, render, noun, keyOf) {
    let open = false;
    const top = new Set(items.slice().sort((a, b) => (b.n - a.n) || (Number(!!b.top) - Number(!!a.top))).slice(0, first).map(keyOf));
    const draw = () => {
      const shown = open ? items : items.filter((x) => top.has(keyOf(x)));
      host.replaceChildren(...shown.map(render));
      btn.hidden = items.length <= first;
      btn.textContent = open ? 'Show fewer' : `Show all ${items.length} ${noun}`;
      btn.setAttribute('aria-expanded', String(open));
    };
    btn.addEventListener('click', () => { open = !open; draw(); if (!open) host.scrollIntoView({ block: 'start' }); });
    draw();
    lists[key] = {
      reveal(id) {
        if (!open && !top.has(id)) { open = true; draw(); }
        const node = host.querySelector(`[data-id="${CSS.escape(id)}"]`);
        if (node) {
          node.scrollIntoView({ block: 'center' });
          node.classList.add('hit');
          setTimeout(() => node.classList.remove('hit'), 2200);
        }
      },
      redraw: draw,
    };
  }

  // ---------------------------------------------------------------- hero
  function renderHero(d) {
    const h = d.hero;
    $('eyebrow').textContent = h.eyebrow;
    $('name').textContent = h.name;
    $('tagline').textContent = h.tagline;
    $('dates').textContent = h.dates;
    $('lede').textContent = h.lede;
    $('hero-img').alt = h.photo.alt;
    $('hero-quote').textContent = h.quote.q;
    $('hero-quote-by').textContent = h.quote.by;
    $('hero-quote-open').addEventListener('click', () => openPassage(ownRef(h.quote)));
    const hp = d.credits.portraits.find((c) => c.name.startsWith(h.name));
    $('hero-credit').replaceChildren(hp.page ? el('a', ext({ class: 'src', href: hp.page }), hp.attribution) : hp.attribution);
  }

  // ---------------------------------------------------------------- his words
  function renderOwn(own) {
    SOURCE = own.source;
    let cat = own.categories[0].key;
    const host = $('own-list'), btn = $('own-more');
    const card = (it) => el('blockquote', { class: 'lj-transcript', 'data-id': it.id },
      el('cite', { class: 'lj-transcript-speaker' }, OWN, it.page != null ? el('span', { class: 'cap' }, `page ${it.page + 1}`) : null),
      // a line that leans on the question before it gets a sentence saying what it answers
      !it.alone && it.sum ? el('p', { class: 'asked' }, el('b', null, 'In answer: '), it.sum) : null,
      el('p', null, it.q),
      el('footer', null, el('span', null, own.source), readIt(ownRef(it))));
    const draw = () => {
      const c = own.categories.find((x) => x.key === cat);
      $('own-definition').textContent = c.definition;
      const items = own.items.filter((i) => i.cat === cat);
      btn.replaceWith(btn.cloneNode(true));      // drop the old list's handler
      expandable('own', items, own.first, host, $('own-more'), card, 'passages on this subject', (x) => x.id);
    };
    const pills = $('own-pills');
    const drawPills = () => pills.replaceChildren(...own.categories.map((c) =>
      el('button', { type: 'button', class: 'lj-rel', 'aria-pressed': String(c.key === cat),
        onclick: () => { cat = c.key; drawPills(); draw(); } }, c.label, ' ', el('span', null, String(c.count)))));
    drawPills();
    draw();
    lists.ownCat = (key) => { if (key !== cat) { cat = key; drawPills(); draw(); } };
  }

  // ---------------------------------------------------------------- journeys
  function renderJourneys(j) {
    const card = (x) => el('article', { class: 'card', 'data-id': x.k },
      el('p', { class: 'eyebrow' }, [x.kind, x.year].filter(Boolean).join(' · ')),
      el('h3', null, x.title),
      el('p', { class: 'qs' }, q(x.q)),
      el('p', { class: 'cap foot' }, x.place ? [x.place, ' · '] : null, readIt(ownRef(x))));
    expandable('journeys', j.items, j.first, $('journey-grid'), $('journey-more'), card, 'journeys, in the order he told them', (x) => x.k);
    $('journeys-lede').textContent = `From the mountains of Morocco to a shrine in Kyoto: ${j.points.length} places in ${j.countries} countries where he played and the people he found there, as he told them. Each point on the map is a story below.`;
    renderMap(j);
  }

  // the map: every geocoded journey, each point a way into its card
  function renderMap(j) {
    const host = $('map');
    if (typeof L === 'undefined') { host.replaceChildren(el('p', { class: 'cap', style: 'padding:16px' }, 'The map library did not load; the places are listed below.')); return; }
    const map = L.map(host, { scrollWheelZoom: false, worldCopyJump: true });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(map);
    const R = { site: 7, town: 9, country: 16 };
    const pts = [];
    for (const p of j.points) {
      const m = L.circleMarker([p.lat, p.lon], { radius: R[p.precision] || 7, color: '#4a8ecb', weight: 1.5,
        fillColor: '#4a8ecb', fillOpacity: p.precision === 'country' ? 0.15 : p.precision === 'town' ? 0.45 : 0.85,
        dashArray: p.precision === 'country' ? '3 3' : null }).addTo(map);
      const body = el('div', null,
        el('b', null, p.title),
        el('span', { class: 'cap', style: 'display:block' }, [p.kind, p.year, p.label !== p.place ? p.place : null].filter(Boolean).join(' · '),
          p.precision !== 'site' ? ` (placed at ${p.precision} level)` : ''),
        el('span', { class: 'cap' },
          p.card ? el('button', { type: 'button', class: 'linkish', onclick: () => lists.journeys.reveal(p.k) }, 'The story') : null,
          p.b ? readIt({ doc: 'own', blocks: p.b }) : null));
      m.bindPopup(body, { maxWidth: 320 });
      pts.push([p.lat, p.lon]);
    }
    map.fitBounds(L.latLngBounds(pts).pad(0.08));
    $('map-key').replaceChildren(
      el('span', null, el('i'), 'Place named'), el('span', null, el('i', { class: 'town' }), 'Town only'), el('span', null, el('i', { class: 'country' }), 'Country only'),
      el('span', null, 'Click a point for the story. Scroll with the + and − buttons.'));
    // tiles are sized to the box: redraw once the section has its final layout
    setTimeout(() => map.invalidateSize(), 300);
  }

  // ---------------------------------------------------------------- records
  function renderRecords(r) {
    const years = r.leader.map((x) => parseInt(x.y, 10)).filter(Boolean);
    $('records-lede').textContent = `He made ${r.leader.length} records under his own name from ${Math.min(...years)} to ${Math.max(...years)}, and he chose their titles with care. These are the records and pieces he talks about in 2009.`;
    const card = (x) => el('article', { class: 'record', 'data-id': x.k },
      el('div', { class: 'title-row' }, el('h3', null, x.title), el('span', { class: 'cap' }, x.year ? String(x.year) : '')),
      el('p', { class: 'qs' }, q(x.q)),
      el('p', { class: 'cap foot' }, [x.kind, x.label].filter(Boolean).join(' · '),
        x.as_transcribed ? ` · transcribed as ${q(x.as_transcribed)}` : '', ' · ', readIt(ownRef(x))));
    expandable('records', r.items, r.first, $('record-grid'), $('record-more'), card, 'records and pieces he talks about', (x) => x.k);

    $('disco-summary').textContent = `Every record under his name (${r.leader.length})`;
    const said = new Set(r.items.map((x) => x.k));
    $('disco-list').replaceChildren(...r.leader.map((d) => el('li', { 'data-id': `leader:${d.t}` },
      el('span', { class: 'y' }, d.y),
      d.cover ? el('img', { class: 'sleeve', src: d.cover, alt: '', loading: 'lazy' }) : el('span', { class: 'sleeve blank' }),
      el('span', null, d.url ? el('a', ext({ href: d.url }), d.t) : d.t,
        d.said && said.has(d.said) ? [' ', el('button', { type: 'button', class: 'linkish said', onclick: () => lists.records.reveal(d.said) }, 'what he said ↑')] : null))));
  }

  // ---------------------------------------------------------------- compositions
  function renderTunes(t) {
    const top = t.items[0];
    const byOthers = (rec) => rec.filter((r) => !r.sampled).map((r) => r.who[0]);
    const names = [...new Set(byOthers(top.rec))];
    $('tunes-lede').textContent = `Other musicians took up his tunes almost as soon as he wrote them. ${q(top.title)} alone has passed through the hands of ${names.slice(0, 3).join(', ')} and ${names[3] || 'others'}: ${t.recordings} recordings of ${t.count} of his tunes, on records with a Wikipedia article.`;
    let sel = top.title, open = false;
    const max = top.n;
    const list = $('tune-list'), btn = $('tune-more');
    const drawRecs = () => {
      const tune = t.items.find((x) => x.title === sel);
      $('tune-title').textContent = `Who recorded ${q(tune.title)}`;
      $('tune-recs').replaceChildren(...tune.rec.map((r) => el('li', null,
        el('span', null, el('b', null, r.who.join(', ')), ' ', el('span', { class: 'cap' }, r.url ? el('a', ext({ class: 'src', href: r.url }), r.rel) : r.rel, r.sampled ? ' (sampled)' : '')),
        el('span', { class: 'cap' }, r.y || ''))));
    };
    const draw = () => {
      const shown = open ? t.items : t.items.slice(0, t.first);
      list.replaceChildren(...shown.map((x) => el('button', { type: 'button', class: 'tune-row', 'aria-pressed': String(x.title === sel), 'data-id': `tune:${x.title}`,
          onclick: () => { sel = x.title; draw(); drawRecs(); } },
        el('span', null, x.title),
        el('span', { class: 'bar' }, el('i', { style: `width:${Math.max(2, Math.round(x.n / max * 100))}%` })),
        el('span', { class: 'n' }, String(x.n)))));
      btn.hidden = t.items.length <= t.first;
      btn.textContent = open ? 'Show fewer' : `Show all ${t.items.length} tunes`;
      btn.setAttribute('aria-expanded', String(open));
    };
    btn.addEventListener('click', () => { open = !open; draw(); });
    draw(); drawRecs();
    lists.tunes = { reveal(title) { sel = title; if (t.items.findIndex((x) => x.title === title) >= t.first) open = true; draw(); drawRecs(); $('tunes').scrollIntoView({ block: 'start' }); } };
  }

  // ---------------------------------------------------------------- people he spoke of
  function renderPeople(p) {
    $('people-lede').textContent = `Idols, bandmates, Gnawa masters, family and old friends: the ${p.count} people he names in his oral history and says something about, in his words. Names are given as the transcript spells them where it differs.`;
    const card = (x) => {
      const more = x.more.length ? el('div', { class: 'person-more' }, ...x.more.map((m) =>
        el('p', { class: 'qs' }, q(m.q), ' ', readIt({ doc: 'own', blocks: m.b, marks: m.marks }, 'Read')))) : null;
      if (more) more.hidden = true;
      return el('article', { class: 'card', 'data-id': x.id },
        el('div', { class: 'person-head' }, avatar(x),
          el('div', null, el('h3', { class: 'lj-person-name' }, x.name), el('p', { class: 'lj-person-meta' }, x.meta || x.line))),
        el('div', { class: 'lj-rel-line' }, el('b', null, OWN), el('span', { class: 'lj-rel static' }, x.rel), el('b', null, x.name)),
        el('p', { class: 'qs' }, q(x.q)),
        more,
        el('p', { class: 'cap foot' },
          x.as_named ? [`Transcribed as ${q(x.as_named)} · `] : null,
          readIt(ownRef(x)),
          more ? [' · ', el('button', { type: 'button', class: 'linkish', 'aria-expanded': 'false', onclick: (e) => {
            more.hidden = !more.hidden; e.target.setAttribute('aria-expanded', String(!more.hidden));
            e.target.textContent = more.hidden ? `${x.more.length} more` : 'Fewer'; } }, `${x.more.length} more`)] : null));
    };
    expandable('people', p.items, p.first, $('people-grid'), $('people-more'), card, 'people he spoke of', (x) => x.id);
  }

  // ---------------------------------------------------------------- who spoke of him
  function renderWitnesses(w) {
    const NUM = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty'];
    const num = (n) => NUM[n] || String(n);
    const left = w.people_in_data - w.people;
    $('witness-lede').textContent = `${num(w.people_in_data).replace(/^./, (c) => c.toUpperCase())} musicians and friends speak of him in their own oral histories, in the Smithsonian and Hamilton College collections. ${num(w.people).replace(/^./, (c) => c.toUpperCase())} of them are here; for the other ${num(left)} the only line is a joke, a fragment or the interviewer's. Each passage opens in its transcript.`;
    const card = (x) => el('blockquote', { class: 'lj-transcript', 'data-id': x.id },
      el('cite', { class: 'lj-transcript-speaker' }, avatar(x), el('span', null, x.name, x.line ? el('span', { class: 'cap', style: 'display:block' }, x.line) : null)),
      el('p', null, x.q),
      x.second ? el('p', { class: 'second' }, x.second) : null,
      x.note ? el('p', { class: 'note' }, x.note) : null,
      el('footer', null, el('span', null, x.src), readIt({ doc: x.doc, blocks: x.blocks, marks: x.marks })));
    expandable('witnesses', w.items, w.first, $('witness-grid'), $('witness-more'), card, 'passages', (x) => x.id);
  }

  // ---------------------------------------------------------------- network
  function renderNetwork(n, hero) {
    const c = n.counts;
    $('network-lede').textContent = `Everyone on this page, around him. ${c.from} he spoke of, ${c.to} spoke of him, and ${c.both === 2 ? 'two' : c.both} did both.`;
    $('network-link').href = n.url;
    const FILL = { both: 'var(--node-red)', to: 'var(--node-periwinkle)', from: 'var(--node-yellow)' };
    const LABEL = { both: 'Linked both ways', to: 'Spoke of him', from: 'He spoke of them' };
    const ARROW = { both: '⟷', to: '⟵', from: '⟶' };
    $('legend').replaceChildren(...['both', 'to', 'from'].map((k) => el('span', null, el('i', { style: `background:${FILL[k]}` }), `${LABEL[k]} · ${c[k]}`, el('span', { class: 'arrow', 'aria-hidden': 'true' }, ARROW[k]))),
      el('span', { class: 'cap' }, 'The arrow points at whoever is spoken of.'));

    const W = 1040, H = Math.max(680, n.nodes.length * 28), cx = W / 2, cy = H / 2, rx = 360, ry = H / 2 - 48, N = n.nodes.length;
    const g = $('graph');
    g.setAttribute('viewBox', `0 0 ${W} ${H}`);
    g.setAttribute('aria-label', `${hero.name} at the centre, linked to ${N} people: ${c.both} both ways, ${c.to} who spoke of him, ${c.from} he spoke of.`);
    g.replaceChildren();
    const edges = [], nodes = [];
    n.nodes.forEach((p, i) => {
      const a = -Math.PI / 2 + (i + 0.5) * 2 * Math.PI / N;
      const x = cx + rx * Math.cos(a), y = cy + ry * Math.sin(a);
      // the label sits beside the node, or above / below it near the poles where
      // neighbours would otherwise run into each other
      // labels sit beside their node; near the poles, where neighbours are
      // almost level, each is pushed away from the pole so the next one clears it
      const c = Math.cos(a), near = Math.max(0, 0.3 - Math.abs(c)) / 0.3;
      const lx = c < 0 ? x - 14 : x + 14, ly = y + 4.5 + (Math.sin(a) < 0 ? -1 : 1) * near * 24;
      // the edge stops short of both discs, and an arrowhead points at whoever
      // is spoken of: outward when he spoke of them, inward when they spoke of him
      const dx = x - cx, dy = y - cy, len = Math.hypot(dx, dy), ux = dx / len, uy = dy / len;
      const x1 = cx + ux * 60, y1 = cy + uy * 60, x2 = x - ux * 12, y2 = y - uy * 12;
      edges.push(svg('line', { class: 'edge' + (p.kind === 'both' ? ' both' : ''),
        x1: x1.toFixed(1), y1: y1.toFixed(1), x2: x2.toFixed(1), y2: y2.toFixed(1),
        'marker-end': p.kind !== 'to' ? 'url(#arrow)' : null,
        'marker-start': p.kind !== 'from' ? 'url(#arrow)' : null }));
      const go = () => {
        const list = p.kind === 'from' ? 'people' : 'witnesses';
        lists[list].reveal(p.kind === 'from' ? p.from : p.to);
      };
      const node = svg('g', { class: 'node', tabindex: '0', role: 'link', 'aria-label': `${p.label}: ${LABEL[p.kind].toLowerCase()}` },
        svg('circle', { cx: x.toFixed(1), cy: y.toFixed(1), r: 8, fill: FILL[p.kind] }),
        svg('text', { x: lx.toFixed(1), y: ly.toFixed(1), 'text-anchor': c < 0 ? 'end' : 'start' }, p.label));
      node.addEventListener('click', go);
      node.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
      nodes.push(node);
    });
    const me = svg('g', { class: 'me' },
      svg('circle', { cx, cy, r: 48 }),
      svg('circle', { class: 'ring', cx, cy, r: 54 }),
      svg('text', { x: cx, y: cy - 4 }, hero.name.split(' ')[0]),
      svg('text', { x: cx, y: cy + 15 }, hero.name.split(' ').slice(1).join(' ')));
    const defs = svg('defs', null, svg('marker', { id: 'arrow', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 9, markerHeight: 9, orient: 'auto-start-reverse', markerUnits: 'userSpaceOnUse' },
      svg('path', { d: 'M0,0 L10,5 L0,10 z', class: 'arrowhead' })));
    g.append(defs, ...edges, me, ...nodes);
  }

  // ---------------------------------------------------------------- search
  function initSearch(d) {
    const input = $('search'), menu = $('search-menu');
    const index = [];
    for (const p of d.people.items) index.push({ label: p.name, kind: 'he spoke of', go: () => lists.people.reveal(p.id) });
    for (const w of d.witnesses.items) index.push({ label: w.name, kind: 'spoke of him', go: () => lists.witnesses.reveal(w.id) });
    for (const t of d.tunes.items) index.push({ label: t.title, kind: 'tune', go: () => lists.tunes.reveal(t.title) });
    for (const r of d.records.items) index.push({ label: r.title, kind: r.kind.toLowerCase() + ' he talks about', go: () => lists.records.reveal(r.k) });
    for (const r of d.records.leader) index.push({ label: r.t, kind: `record, ${r.y}`, go: () => {
      $('disco').open = true;
      const li = $('disco-list').querySelector(`[data-id="${CSS.escape('leader:' + r.t)}"]`);
      if (li) { li.scrollIntoView({ block: 'center' }); li.classList.add('hit'); setTimeout(() => li.classList.remove('hit'), 2200); }
    } });
    for (const j of d.journeys.items) index.push({ label: j.title, kind: j.place ? `journey · ${j.place}` : 'journey', go: () => lists.journeys.reveal(j.k) });
    for (const c of d.own.categories) index.push({ label: c.label, kind: 'in his own words', go: () => { lists.ownCat(c.key); $('voices').scrollIntoView({ block: 'start' }); } });
    const fold = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    let hits = [], sel = -1;
    const close = () => { menu.hidden = true; input.setAttribute('aria-expanded', 'false'); sel = -1; };
    const pick = (h) => { close(); input.value = ''; h.go(); };
    const draw = () => {
      menu.replaceChildren(...(hits.length ? hits.map((h, i) => el('li', { role: 'option', 'aria-selected': String(i === sel), onmousedown: (e) => { e.preventDefault(); pick(h); } },
        el('span', null, h.label), el('span', null, h.kind))) : [el('li', { class: 'none' }, 'Nothing on this page by that name')]));
      menu.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    };
    input.addEventListener('input', () => {
      const v = fold(input.value.trim());
      if (v.length < 2) return close();
      const words = v.split(/\s+/);
      hits = index.filter((h) => { const l = fold(h.label); return words.every((w) => l.includes(w)); }).slice(0, 12);
      sel = hits.length ? 0 : -1;
      draw();
    });
    input.addEventListener('keydown', (e) => {
      if (menu.hidden) return;
      if (e.key === 'ArrowDown') { sel = Math.min(hits.length - 1, sel + 1); draw(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); }
      else if (e.key === 'Enter') { e.preventDefault(); if (hits[sel]) pick(hits[sel]); }
      else if (e.key === 'Escape') close();
    });
    input.addEventListener('blur', close);
    $('search-form').addEventListener('submit', (e) => { e.preventDefault(); if (hits[sel]) pick(hits[sel]); });
  }

  // ---------------------------------------------------------------- nav, sources, credits
  function initNav() {
    const links = [...document.querySelectorAll('.lj-nav a')];
    const targets = links.map((a) => document.querySelector(a.getAttribute('href')));
    const io = new IntersectionObserver((entries) => {
      for (const en of entries) {
        if (!en.isIntersecting) continue;
        const i = targets.indexOf(en.target);
        links.forEach((a, k) => { if (k === i) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current'); });
      }
    }, { rootMargin: '-40% 0px -50% 0px' });
    targets.forEach((t) => t && io.observe(t));
  }

  function renderSources(d) {
    const s = d.sources;
    $('sources-list').replaceChildren(
      el('li', null, s.own.title, ' ', el('a', ext({ class: 'src', href: s.own.pdf }), 'Transcript (PDF)'), '. Quotations are verbatim from the transcript, which spells names by ear (“Louie Armstrong”, “Paul Robinson”, “Tangiers”); they have not been corrected.'),
      el('li', null, `Oral histories from the Smithsonian Jazz Oral History Program and the Hamilton College Fillius Jazz Archive, as linked beside each passage. ${s.interviews} interviews in the Linked Jazz collection name him.`),
      el('li', null, 'Discography and recordings of his compositions from English Wikipedia album articles; the list of records under his name from his Wikipedia discography; sleeves from MusicBrainz and the Cover Art Archive; dates and places from ', el('a', ext({ class: 'src', href: s.wikidata }), 'Wikidata'), '.'),
      el('li', null, 'Elsewhere: ', ...d.links.flatMap((l, i) => [i ? ' · ' : null, el('a', ext({ class: 'src', href: l.url }), l.label)])));
    $('credits').replaceChildren(
      ...d.credits.portraits.map((p) => el('li', null, p.name + ': ', p.page ? el('a', ext({ class: 'src', href: p.page }), p.attribution) : p.attribution)),
      el('li', null, d.credits.covers));
  }

  fetch(versioned('data.json'))
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => {
      initPassage();
      renderHero(d);
      renderOwn(d.own);
      renderJourneys(d.journeys);
      renderRecords(d.records);
      renderTunes(d.tunes);
      renderPeople(d.people);
      renderWitnesses(d.witnesses);
      renderNetwork(d.network, d.hero);
      renderSources(d);
      initSearch(d);
      initNav();
    })
    .catch((e) => {
      document.body.prepend(el('p', { style: 'padding:20px 32px;color:#b3261e' },
        `The page data could not be loaded (${e.message}).`));
    });
})();
