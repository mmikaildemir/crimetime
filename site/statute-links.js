// Statute citations → links to the NYPTI statute browser.
//
// NYPTI URLs are https://statutes.nypti.org/$$<LAW><SECTION>$$, where <LAW> is the
// NYS Open Legislation law code (PEN, CPL, VAT, EXC, COR, NAV) and <SECTION> is the
// section number, e.g. $$PEN60.01$$, $$VAT1192$$, $$EXC995-C$$. Subdivisions are not
// addressable ($$PEN60.01(1)$$ is a blank page), so "PL 60.35(1)(a)" links to 60.35.
// Articles use an "A" prefix, but only for laws whose articles are flat in Open
// Legislation: $$CORA6-C$$ works, while Penal Law articles (nested under parts and
// titles) have no NYPTI page, so "PL Art. 105" stays plain text.
//
// Once loaded, this file watches the page and links every citation in rendered text,
// so render code needs no changes. Text inside links, buttons, form controls and <pre>
// is left alone.
(function () {
  const BASE = 'https://statutes.nypti.org/';

  // Name as written → [law code, sections always dotted?]. Longest names first.
  const LAWS = [
    ['Criminal Procedure Law', 'CPL', true], ['C.P.L.', 'CPL', true], ['CPL', 'CPL', true],
    ['Penal Law', 'PEN', true], ['P.L.', 'PEN', true], ['PL', 'PEN', true],
    ['Vehicle and Traffic Law', 'VAT', false], ['V&T Law', 'VAT', false], ['VTL', 'VAT', false],
    ['Executive Law', 'EXC', false], ['Exec. Law', 'EXC', false], ['Exec Law', 'EXC', false],
    ['Correction Law', 'COR', false], ['Corr. Law', 'COR', false], ['Corr Law', 'COR', false],
    ['Navigation Law', 'NAV', false], ['NAV', 'NAV', false],
  ];
  const LAW_BY_NAME = new Map(LAWS.map(([name, code, dotted]) => [name.toLowerCase(), { code, dotted }]));
  const ARTICLE_LAWS = new Set(['COR']);

  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\&]/g, '\\$&');
  const LAW_ALT = LAWS.map(([name]) => esc(name).replace(/ /g, '\\s+')).join('|');

  // Where a citation starts: a law name (optionally followed by §), or a bare § (Penal Law).
  const START = new RegExp(`(?<![\\w.&])(?:(${LAW_ALT})(?![\\w])\\s*(?:§§?\\s*)?|(§§?)\\s*)`, 'gi');
  // Subdivisions, incl. ranges and alternatives: (1)(a)(ii), (2)-(4), (2)/(2-a), (2-a)
  const SUBS = '(?:[\\/\\u2013-]?\\([0-9A-Za-z-]{1,10}\\))*';
  const SECTION = {
    true: new RegExp(`(\\d+\\.\\d+(?:-[A-Za-z]+)?)${SUBS}(?![\\w])`, 'y'),
    false: new RegExp(`(\\d+(?:-[A-Za-z]+)?(?:\\.\\d+)?)${SUBS}(?![\\w])`, 'y'),
  };
  const ARTICLE = /(?:art(?:icle)?\.?)\s*(\d+(?:-[A-Za-z]+)?)(?![\w])/iy;
  // Further sections under the same law: "PL 60.21, 65.00", "PL 70.70 / 70.71".
  // Laws with undotted sections need an explicit § so "VTL 1192, 3 times" stays plain.
  const MORE = { true: /(\s*(?:,|\/|\band\b|\bor\b|&)\s*(?:§§?\s*)?)/iy, false: /(\s*(?:,|\/|\band\b|\bor\b|&)\s*§§?\s*)/iy };

  function nyptiUrl(code, section, isArticle) {
    return `${BASE}$$${code}${isArticle ? 'A' : ''}${section.toUpperCase()}$$`;
  }

  // Split a string into plain text and {text, href} pieces. Returns null when there is no citation.
  function parse(text) {
    const parts = [];
    let last = 0, found = false;
    START.lastIndex = 0;
    let m;
    while ((m = START.exec(text))) {
      const law = m[1] ? LAW_BY_NAME.get(m[1].replace(/\s+/g, ' ').toLowerCase()) : { code: 'PEN', dotted: true };
      let pos = START.lastIndex;
      const pieces = [];

      if (m[1]) {
        ARTICLE.lastIndex = pos;
        const a = ARTICLE.exec(text);
        if (a) {
          if (ARTICLE_LAWS.has(law.code)) {
            pieces.push({ from: m.index, to: ARTICLE.lastIndex, href: nyptiUrl(law.code, a[1], true) });
          }
          pos = ARTICLE.lastIndex;
        }
      }
      if (!pieces.length && pos === START.lastIndex) {
        const re = SECTION[law.dotted];
        re.lastIndex = pos;
        let s = re.exec(text);
        if (s) {
          pieces.push({ from: m.index, to: re.lastIndex, href: nyptiUrl(law.code, s[1]) });
          pos = re.lastIndex;
          for (;;) {
            const more = MORE[law.dotted];
            more.lastIndex = pos;
            const sep = more.exec(text);
            if (!sep) break;
            re.lastIndex = more.lastIndex;
            s = re.exec(text);
            if (!s) break;
            pieces.push({ from: more.lastIndex, to: re.lastIndex, href: nyptiUrl(law.code, s[1]) });
            pos = re.lastIndex;
          }
        }
      }
      for (const p of pieces) {
        if (p.from > last) parts.push(text.slice(last, p.from));
        parts.push({ text: text.slice(p.from, p.to), href: p.href });
        last = p.to;
        found = true;
      }
      START.lastIndex = Math.max(pos, m.index + 1);
    }
    if (!found) return null;
    if (last < text.length) parts.push(text.slice(last));
    return parts;
  }

  const SKIP = 'a, button, input, textarea, select, option, script, style, pre, [contenteditable], [data-no-statute-links]';

  function linkifyTextNode(node) {
    const parent = node.parentElement;
    if (!parent || parent.closest(SKIP)) return;
    const parts = parse(node.nodeValue);
    if (!parts) return;
    const frag = document.createDocumentFragment();
    for (const p of parts) {
      if (typeof p === 'string') { frag.appendChild(document.createTextNode(p)); continue; }
      const a = document.createElement('a');
      a.className = 'statute-link';
      a.href = p.href;
      a.target = '_blank';
      a.rel = 'noopener';
      a.title = `Open ${p.text.trim()} on NYPTI Statutes`;
      a.textContent = p.text;
      frag.appendChild(a);
    }
    parent.replaceChild(frag, node);
  }

  function linkify(root) {
    if (root.nodeType === Node.TEXT_NODE) return linkifyTextNode(root);
    if (root.nodeType !== Node.ELEMENT_NODE || root.closest(SKIP)) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => /\d/.test(n.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(linkifyTextNode);
  }

  window.StatuteLinks = { parse, linkify, nyptiUrl };
  if (typeof document === 'undefined') return;

  // Batch DOM changes and link them once per frame. The nodes this creates contain no
  // unlinked citations, so the observer does not loop.
  let pending = new Set(), scheduled = false;
  const flush = () => {
    scheduled = false;
    const roots = [...pending];
    pending = new Set();
    for (const n of roots) if (n.isConnected) linkify(n);
  };
  const observer = new MutationObserver((records) => {
    for (const r of records) {
      if (r.type === 'characterData') pending.add(r.target);
      else r.addedNodes.forEach(n => pending.add(n));
    }
    if (pending.size && !scheduled) { scheduled = true; requestAnimationFrame(flush); }
  });

  function start() {
    linkify(document.body);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
