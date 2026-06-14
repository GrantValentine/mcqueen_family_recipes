"""Patch base.html: replace vine JS + aura HTML block with clean version.

Finds the block from <!-- Blue Willow laurel vine --> through the LAST
<!-- ... End Aura ... --> comment and replaces it with fresh VINE_JS + NEW_AURA.
Skips the CSS step (already applied in a previous run; checked for idempotency).
"""
import pathlib, re

# ── CSS sentinel (must already be present) ────────────────────────────────────
EXPECTED_CSS_SENTINEL = "@keyframes wf-fade"

# ── New aura HTML (clean, single div) ─────────────────────────────────────────
AURA_OPEN  = "  <!-- Blue Willow Aura -->"
AURA_CLOSE = "  <!-- /Blue Willow Aura -->"

NEW_AURA = (
    AURA_OPEN + "\n"
    "  <div class=\"wf-aura\" aria-hidden=\"true\" id=\"wf-aura\">\n"
    "    <svg id=\"wf-svg\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"></svg>\n"
    "  </div>\n"
    + AURA_CLOSE
)

# ── Vine generation JS ─────────────────────────────────────────────────────────
VINE_JS = r"""  <!-- Blue Willow laurel vine — JS-generated, no pre-written nodes -->
  <script>
  (function () {
    var NS = 'http://www.w3.org/2000/svg', B = '#1f2ca3';
    var isFirst = document.documentElement.classList.contains('wf-first');

    function r(n) { return Math.round(n * 10) / 10; }

    /* Gently wavy rounded-rectangle stem path */
    function stemD(W, H, ins) {
      var cr = Math.min(50, W * 0.04);
      var x0 = ins, y0 = ins, x1 = W - ins, y1 = H - ins;
      var k = cr * 0.552;
      var wa = 3.5;
      var ww = Math.min(80, (x1 - x0) * 0.18);
      return [
        'M '  + r(x0+cr)     + ',' + r(y0),
        'C '  + r(x0+cr+ww)  + ',' + r(y0-wa)    + ' ' + r(x1-cr-ww)  + ',' + r(y0+wa)    + ' ' + r(x1-cr)  + ',' + r(y0),
        'C '  + r(x1-cr+k)   + ',' + r(y0)        + ' ' + r(x1)        + ',' + r(y0+cr-k)  + ' ' + r(x1)     + ',' + r(y0+cr),
        'C '  + r(x1+wa)     + ',' + r(y0+cr+ww)  + ' ' + r(x1-wa)     + ',' + r(y1-cr-ww) + ' ' + r(x1)     + ',' + r(y1-cr),
        'C '  + r(x1)        + ',' + r(y1-cr+k)   + ' ' + r(x1-cr+k)   + ',' + r(y1)       + ' ' + r(x1-cr)  + ',' + r(y1),
        'C '  + r(x1-cr-ww)  + ',' + r(y1+wa)     + ' ' + r(x0+cr+ww)  + ',' + r(y1-wa)    + ' ' + r(x0+cr)  + ',' + r(y1),
        'C '  + r(x0+cr-k)   + ',' + r(y1)        + ' ' + r(x0)        + ',' + r(y1-cr+k)  + ' ' + r(x0)     + ',' + r(y1-cr),
        'C '  + r(x0-wa)     + ',' + r(y1-cr-ww)  + ' ' + r(x0+wa)     + ',' + r(y0+cr+ww) + ' ' + r(x0)     + ',' + r(y0+cr),
        'C '  + r(x0)        + ',' + r(y0+cr-k)   + ' ' + r(x0+cr-k)   + ',' + r(y0)       + ' ' + r(x0+cr)  + ',' + r(y0),
        'Z'
      ].join(' ');
    }

    function mkEl(tag, attrs) {
      var e = document.createElementNS(NS, tag);
      for (var k in attrs) e.setAttribute(k, attrs[k]);
      return e;
    }

    /* Almond leaf — opacity-only animation (no CSS transform conflict) */
    function addLeaf(par, px, py, deg, sc, dl) {
      var ln = r(10 * sc), h = r(2.6 * sc);
      var g = mkEl('g', {
        transform: 'translate(' + r(px) + ',' + r(py) + ') rotate(' + r(deg) + ')',
        class: 'wf-lf'
      });
      if (dl != null) g.style.animationDelay = dl + 'ms';
      g.appendChild(mkEl('path', {
        d: 'M 0,0 C 1.5,' + (-h) + ' ' + r(ln-1.5) + ',' + (-h) + ' ' + ln + ',0'
         + ' C ' + r(ln-1.5) + ',' + h + ' 1.5,' + h + ' 0,0 Z',
        fill: B, 'fill-opacity': '0.30'
      }));
      g.appendChild(mkEl('line', {
        x1: '0.3', y1: '0', x2: r(ln - 0.3), y2: '0',
        stroke: B, 'stroke-opacity': '0.80', 'stroke-width': '0.5', 'stroke-linecap': 'round'
      }));
      par.appendChild(g);
    }

    /* 5-petal rose — outer g: SVG position; inner g: CSS bloom */
    function addRose(par, px, py, deg, dl) {
      var pos  = mkEl('g', { transform: 'translate(' + r(px) + ',' + r(py) + ') rotate(' + r(deg) + ')' });
      var anim = mkEl('g', { class: 'wf-fl' });
      if (dl != null) anim.style.animationDelay = dl + 'ms';
      for (var k = 0; k < 5; k++) {
        var pg = mkEl('g', { transform: 'rotate(' + (k * 72) + ')' });
        pg.appendChild(mkEl('path', {
          d: 'M 0,0 Q 1.8,-4.8 9.5,0 Q 1.8,4.8 0,0 Z',
          fill: B, 'fill-opacity': '0.50', stroke: B, 'stroke-width': '0.3', 'stroke-opacity': '0.55'
        }));
        anim.appendChild(pg);
      }
      anim.appendChild(mkEl('circle', { r: '2.7', fill: B, 'fill-opacity': '0.92' }));
      anim.appendChild(mkEl('circle', { r: '1.0', fill: 'white', 'fill-opacity': '0.88' }));
      [0,72,144,216,288].forEach(function(a) {
        var sg = mkEl('g', { transform: 'rotate(' + (a + 36) + ')' });
        sg.appendChild(mkEl('circle', { cx: '4.0', cy: '0', r: '0.6', fill: B, 'fill-opacity': '0.75' }));
        anim.appendChild(sg);
      });
      pos.appendChild(anim);
      par.appendChild(pos);
    }

    /* Forget-me-not cluster */
    function addFME(par, px, py, deg, dl) {
      var pos  = mkEl('g', { transform: 'translate(' + r(px) + ',' + r(py) + ') rotate(' + r(deg) + ')' });
      var anim = mkEl('g', { class: 'wf-fl' });
      if (dl != null) anim.style.animationDelay = dl + 'ms';
      [[-5,-4],[5,-3],[-2,5],[4,4]].forEach(function(off) {
        var fg = mkEl('g', { transform: 'translate(' + off[0] + ',' + off[1] + ')' });
        for (var k = 0; k < 5; k++) {
          var pg = mkEl('g', { transform: 'rotate(' + (k * 72) + ')' });
          pg.appendChild(mkEl('path', {
            d: 'M 0,0 Q 0.5,-2.6 5.2,0 Q 0.5,2.6 0,0 Z',
            fill: B, 'fill-opacity': '0.50'
          }));
          fg.appendChild(pg);
        }
        fg.appendChild(mkEl('circle', { r: '1.2', fill: B, 'fill-opacity': '0.92' }));
        anim.appendChild(fg);
      });
      pos.appendChild(anim);
      par.appendChild(pos);
    }

    /* Tiny bud */
    function addBud(par, px, py, deg, dl) {
      var g = mkEl('g', {
        transform: 'translate(' + r(px) + ',' + r(py) + ') rotate(' + r(deg) + ')',
        class: 'wf-lf'
      });
      if (dl != null) g.style.animationDelay = dl + 'ms';
      g.appendChild(mkEl('line', { x1:'0', y1:'0', x2:'4', y2:'0', stroke:B, 'stroke-opacity':'0.60', 'stroke-width':'0.5' }));
      g.appendChild(mkEl('path', { d:'M 4,0 Q 4.5,-1.8 7.5,-0.3 Q 8,0 7.5,0.3 Q 4.5,1.8 4,0 Z', fill:B, 'fill-opacity':'0.42' }));
      par.appendChild(g);
    }

    function build() {
      var svg = document.getElementById('wf-svg');
      if (!svg) return;
      svg.innerHTML = '';

      var W = window.innerWidth, H = window.innerHeight;
      svg.setAttribute('width',   W);
      svg.setAttribute('height',  H);
      svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);

      var mob   = W < 640, tab = W < 1024;
      var ins   = mob ? 18 : tab ? 22 : 28;
      var lstep = mob ? 0  : tab ? 21 : 16;
      var fstep = mob ? 0  : tab ? 130 : 110;

      var stem = mkEl('path', {
        id: 'wf-stem', d: stemD(W, H, ins), fill: 'none',
        stroke: B, 'stroke-opacity': '1', 'stroke-width': '1.25',
        'stroke-linecap': 'round', 'stroke-linejoin': 'round'
      });
      svg.appendChild(stem);

      var tot = stem.getTotalLength();
      stem.setAttribute('stroke-dasharray',  r(tot));
      stem.setAttribute('stroke-dashoffset', r(tot));

      if (!lstep) {
        stem.setAttribute('stroke-dashoffset', '0');
        return;
      }

      var fol   = mkEl('g', { id: 'wf-foliage' });
      svg.appendChild(fol);

      var DUR   = 2000;
      var nextF = fstep * 0.45;
      var ft    = 0;

      for (var d = 8; d < tot - 8; d += lstep) {
        var t   = d / tot;
        var dl  = isFirst ? Math.round(t * DUR * 0.88) : null;
        var pt  = stem.getPointAtLength(d);
        var pt2 = stem.getPointAtLength(Math.min(d + 1.5, tot - 0.5));
        var ang = Math.atan2(pt2.y - pt.y, pt2.x - pt.x) * 180 / Math.PI;

        if (fstep && d >= nextF) {
          var fa = ang + (Math.random() * 28 - 14);
          if (ft % 2 === 0) addRose(fol, pt.x, pt.y, fa, dl);
          else              addFME (fol, pt.x, pt.y, fa, dl);
          ft++;
          nextF += fstep + Math.random() * 30 - 15;
        }

        var sc   = 0.85 + Math.random() * 0.30;
        var fan  = 55   + Math.random() * 10 - 5;
        var skip = Math.random() < 0.07;
        if (!skip || Math.random() < 0.5) addLeaf(fol, pt.x, pt.y, ang + fan, sc, dl);
        if (!skip || Math.random() < 0.5) addLeaf(fol, pt.x, pt.y, ang - fan, sc, dl);
        if (Math.random() < 0.04)
          addBud(fol, pt.x, pt.y, ang + (Math.random() < 0.5 ? 72 : -72), dl);
      }

      if (isFirst) {
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            stem.style.transition       = 'stroke-dashoffset 2s ease-out';
            stem.style.strokeDashoffset = '0';
          });
        });
      } else {
        stem.setAttribute('stroke-dashoffset', '0');
      }
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () {
        build();
        var t;
        window.addEventListener('resize', function () { clearTimeout(t); t = setTimeout(build, 160); });
      });
    } else {
      build();
      var t;
      window.addEventListener('resize', function () { clearTimeout(t); t = setTimeout(build, 160); });
    }
  })();
  </script>"""

# ── Patch base.html ────────────────────────────────────────────────────────────
p = pathlib.Path("templates/base.html")
html = p.read_text(encoding="utf-8")

# ── Check CSS is already correct ───────────────────────────────────────────────
if EXPECTED_CSS_SENTINEL not in html:
    raise RuntimeError("CSS sentinel '@keyframes wf-fade' not found. Run full CSS patch first.")
print("[1] CSS already correct — skipping.")

# ── Replace vine JS + aura block in ONE pass ───────────────────────────────────
# Find start: the vine JS comment line
VINE_COMMENT = "  <!-- Blue Willow laurel vine"
vine_start = html.find(VINE_COMMENT)
if vine_start == -1:
    raise RuntimeError("Vine JS comment not found in template.")

# Find end: the LAST "End Aura" comment (handles any duplicate aura divs)
last_end_aura_end = -1
search_pos = vine_start
while True:
    comment_start = html.find("<!--", search_pos)
    if comment_start == -1:
        break
    comment_end = html.find("-->", comment_start)
    if comment_end == -1:
        break
    comment_end += 3  # include the -->
    if "End Aura" in html[comment_start:comment_end]:
        last_end_aura_end = comment_end
    search_pos = comment_end

if last_end_aura_end == -1:
    raise RuntimeError("No 'End Aura' comment found after vine JS start.")

# Replacement = clean vine JS + one blank line + clean aura div
replacement = VINE_JS + "\n\n  " + NEW_AURA

html = html[:vine_start] + replacement + html[last_end_aura_end:]
print("[2] Vine JS + aura block replaced (single pass).")

p.write_text(html, encoding="utf-8")
print(f"\nDone. File now {len(html):,} chars.")

# ── Verify ─────────────────────────────────────────────────────────────────────
wf_svg_count  = html.count('id="wf-svg"')
vine_count    = html.count("Blue Willow laurel vine")
end_aura_count = html.count("End Aura")
open_aura_count = html.count('id="wf-aura"')
print(f"\nVerification:")
print(f"  id='wf-svg'   : {wf_svg_count}  (expect 1)")
print(f"  id='wf-aura'  : {open_aura_count}  (expect 1)")
print(f"  Vine JS blocks: {vine_count}  (expect 1)")
print(f"  End Aura cmts : {end_aura_count}  (expect 1)")
