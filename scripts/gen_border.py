"""Generate Blue Willow geometric border SVG for base.html."""
import math, sys

B = "#1f2ca3"
def f(n): return f"{n:.2f}"
def polar(deg, r, ox=0, oy=0):
    a = math.radians(deg)
    return ox + r*math.cos(a), oy + r*math.sin(a)

# ── petal (almond via two quadratic beziers) ────────────────
def petal_d(cx, cy, deg, ln, pw):
    a = math.radians(deg); pa = a + math.pi/2
    tx = cx + ln*math.cos(a); ty = cy + ln*math.sin(a)
    mx = cx + ln*.5*math.cos(a); my = cy + ln*.5*math.sin(a)
    c1x = mx + pw*math.cos(pa); c1y = my + pw*math.sin(pa)
    c2x = mx - pw*math.cos(pa); c2y = my - pw*math.sin(pa)
    return f"M {f(cx)},{f(cy)} Q {f(c1x)},{f(c1y)} {f(tx)},{f(ty)} Q {f(c2x)},{f(c2y)} {f(cx)},{f(cy)} Z"

# ── annular sector (0°→90°) ─────────────────────────────────
def sector_d(r0, r1):
    x0s,y0s = polar(0,r0);  x0e,y0e = polar(90,r0)
    x1e,y1e = polar(90,r1); x1s,y1s = polar(0,r1)
    return (f"M {f(x0s)},{f(y0s)} A {f(r0)},{f(r0)} 0 0,1 {f(x0e)},{f(y0e)} "
            f"L {f(x1e)},{f(y1e)} A {f(r1)},{f(r1)} 0 0,0 {f(x1s)},{f(y1s)} Z")

# ── 4-petal daisy ───────────────────────────────────────────
def daisy(cx, cy, ln=10, pw=4.5, sa=45, i0=0, pop=0.40, cr=3.5):
    out = []
    for k in range(4):
        d = petal_d(cx, cy, sa + k*90, ln, pw)
        out.append(f'<path class="wf-dot" style="--i:{i0+k}" fill="{B}" fill-opacity="{pop}" stroke="none" d="{d}"/>')
    out.append(f'<circle class="wf-dot" style="--i:{i0+4}" cx="{f(cx)}" cy="{f(cy)}" r="{f(cr)}" fill="{B}" fill-opacity="0.88" stroke="none"/>')
    out.append(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(cr*.42)}" fill="white" fill-opacity="0.90" stroke="none"/>')
    return "\n".join(out)

# ── almond leaf ─────────────────────────────────────────────
def leaf(cx, cy, deg, ln=10, pw=4, i=0):
    d = petal_d(cx, cy, deg, ln/2, pw/2)
    return f'<path class="wf-dot" style="--i:{i}" fill="{B}" fill-opacity="0.52" stroke="none" d="{d}"/>'

# ══════════════════════════════════════════════════════════════
# CORNER CONTENT (160×160 viewBox, fan at 0,0 → 0°–90°)
# ══════════════════════════════════════════════════════════════
o = []

# — Fan rings (alternating wash/full) —
rings = [(8,28,0.58,1),(28,50,0.28,2),(50,74,0.55,3),(74,100,0.26,4)]
for ri,(r0,r1,op,iv) in enumerate(rings):
    o.append(f'<path class="wf-dot" style="--i:{iv}" fill="{B}" fill-opacity="{op}" stroke="none" d="{sector_d(r0,r1)}"/>')
    # scallop circles on outer arc edge
    sc_r = (r1-r0)*0.40
    n_sc = max(2, round(math.pi/2*r1 / (sc_r*2.7)))
    sc_op = 0.78 if ri%2==0 else 0.44
    for j in range(n_sc):
        ang = (j+.5)/n_sc*90
        sx,sy = polar(ang,r1)
        o.append(f'<circle class="wf-dot" style="--i:{iv+1}" cx="{f(sx)}" cy="{f(sy)}" r="{f(sc_r)}" fill="{B}" fill-opacity="{sc_op}" stroke="none"/>')

# — Fan rib lines —
for ang in range(0,91,15):
    x0,y0=polar(ang,8); x1,y1=polar(ang,100)
    o.append(f'<line x1="{f(x0)}" y1="{f(y0)}" x2="{f(x1)}" y2="{f(y1)}" stroke="{B}" stroke-opacity="0.28" stroke-width="0.7" stroke-linecap="round"/>')

# — Outer arc border line —
o.append(f'<path d="M 100,0 A 100,100 0 0,1 0,100" fill="none" stroke="{B}" stroke-opacity="0.55" stroke-width="1.1"/>')
# — Inner arc border line —
o.append(f'<path d="M 8,0 A 8,8 0 0,1 0,8" fill="none" stroke="{B}" stroke-opacity="0.65" stroke-width="1.1"/>')

# — Corner apex daisy (at fan pivot 0,0) —
o.append(daisy(0,0, ln=7,pw=3.2,sa=45,i0=1,pop=0.52,cr=3.0))

# — Daisy along top edge —
o.append(daisy(106,19, ln=13,pw=5.8,sa=45,i0=7,pop=0.38))

# — Daisy along left edge —
o.append(daisy(19,106, ln=13,pw=5.8,sa=45,i0=7,pop=0.38))

# — Diagonal leaf sprig from (138,138) toward TL —
sa_r = math.radians(225)
bx,by = 138,138
ex = bx + 28*math.cos(sa_r); ey = by + 28*math.sin(sa_r)
o.append(f'<line class="wf-path" style="--i:9" x1="{f(bx)}" y1="{f(by)}" x2="{f(ex)}" y2="{f(ey)}" stroke="{B}" stroke-opacity="0.50" stroke-width="1.25" stroke-linecap="round"/>')
for lk in range(3):
    lx = bx + lk*14*math.cos(sa_r)
    ly = by + lk*14*math.sin(sa_r)
    perp_a = math.radians(225+90)
    for side in [1,-1]:
        ox = lx + 4*math.cos(perp_a)*side
        oy = ly + 4*math.sin(perp_a)*side
        o.append(leaf(ox,oy, 225+side*55, ln=11,pw=4.5,i=10+lk))

# — Berry cluster near top-right of corner —
bcx,bcy = 130,47
br = 4.0; hr = br*2.1
for k,ang in enumerate([0,60,120,180,240,300]):
    bkx=bcx+hr*math.cos(math.radians(ang)); bky=bcy+hr*math.sin(math.radians(ang))
    o.append(f'<circle class="wf-dot" style="--i:{12+k}" cx="{f(bkx)}" cy="{f(bky)}" r="{br}" fill="{B}" fill-opacity="0.48" stroke="none"/>')
    o.append(f'<circle cx="{f(bkx)}" cy="{f(bky)}" r="{f(br*.40)}" fill="{B}" fill-opacity="0.90" stroke="none"/>')
o.append(f'<circle class="wf-dot" style="--i:12" cx="{bcx}" cy="{bcy}" r="{br}" fill="{B}" fill-opacity="0.55" stroke="none"/>')
o.append(f'<circle cx="{bcx}" cy="{bcy}" r="{f(br*.40)}" fill="{B}" fill-opacity="0.90" stroke="none"/>')
# Berry stem
o.append(f'<line class="wf-path" style="--i:11" x1="{f(bcx)}" y1="{f(bcy+hr)}" x2="{f(bcx+5)}" y2="{f(bcy+hr+13)}" stroke="{B}" stroke-opacity="0.50" stroke-width="1.25" stroke-linecap="round"/>')

# — Fading dots along top and left edges —
for dp in [38,55,72,92,114,136]:
    op = max(0.14, 0.44 - dp/320)
    o.append(f'<circle class="wf-dot" style="--i:14" cx="{dp}" cy="10" r="2.0" fill="{B}" fill-opacity="{op:.2f}" stroke="none"/>')
    o.append(f'<circle class="wf-dot" style="--i:14" cx="10" cy="{dp}" r="2.0" fill="{B}" fill-opacity="{op:.2f}" stroke="none"/>')

corner_out = "\n      ".join(o)

# ══════════════════════════════════════════════════════════════
print("=== CORNER ===")
print(corner_out)
print()

# ══════════════════════════════════════════════════════════════
# EDGE GARLANDS
# ══════════════════════════════════════════════════════════════

# Top edge garland (viewBox="0 0 100 20", stretches horizontally)
print("=== TOP/BOTTOM EDGE ===")
e = []
e.append(f'<path class="wf-path" style="--i:1" d="M 0,14 C 20,10 40,16 60,12 C 80,8 90,14 100,12" fill="none" stroke="{B}" stroke-opacity="0.48" stroke-width="1.1" stroke-linecap="round"/>')
for dx in [10,28,50,72,90]:
    op = 0.38; r_d = 1.7
    e.append(f'<circle class="wf-dot" style="--i:2" cx="{dx}" cy="13" r="{r_d}" fill="{B}" fill-opacity="{op}" stroke="none"/>')
for dx in [20,50,80]:
    e.append(f'<circle class="wf-dot" style="--i:3" cx="{dx}" cy="12" r="2.5" fill="{B}" fill-opacity="0.30" stroke="none"/>')
    e.append(f'<circle cx="{dx}" cy="12" r="1.0" fill="{B}" fill-opacity="0.78" stroke="none"/>')
print("\n      ".join(e))
print()

# Left edge garland (viewBox="0 0 20 100", stretches vertically)
print("=== LEFT/RIGHT EDGE ===")
r2 = []
r2.append(f'<path class="wf-path" style="--i:1" d="M 14,0 C 10,20 16,40 12,60 C 8,80 14,90 12,100" fill="none" stroke="{B}" stroke-opacity="0.48" stroke-width="1.1" stroke-linecap="round"/>')
for dy in [10,28,50,72,90]:
    r2.append(f'<circle class="wf-dot" style="--i:2" cx="13" cy="{dy}" r="1.7" fill="{B}" fill-opacity="0.38" stroke="none"/>')
for dy in [20,50,80]:
    r2.append(f'<circle class="wf-dot" style="--i:3" cx="12" cy="{dy}" r="2.5" fill="{B}" fill-opacity="0.30" stroke="none"/>')
    r2.append(f'<circle cx="12" cy="{dy}" r="1.0" fill="{B}" fill-opacity="0.78" stroke="none"/>')
print("\n      ".join(r2))
