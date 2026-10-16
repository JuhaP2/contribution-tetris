"""Render an animated retro space shooter as an SVG for a GitHub profile.

A ship clears a marching alien formation, survives a WARNING, and takes
down a boss. The score climbs with every hit and finishes at the user's
contribution count for the last year.

Usage: GITHUB_TOKEN=... python invaders.py <user> <out_dir>
"""
import datetime
import math
import os
import random
import sys

from tetris import fetch_total

AUTHOR = "@JuhaP2"     # made by tag, intentionally not taken from the user argument

W, H = 720, 300
HUD = 30
GROUND = 288
DT = 0.04
EPS = 0.004

P = 3                  # alien and ship pixel size
COLS, ROWS = 11, 5
CX, CY = 42, 30        # formation spacing
STEP, DOWN = 10, 10
FY_MAX = 86

PLAYER_Y = 262
PSPEED = 230
BSPEED = 520
BOMB_SPEED = 170
BOSS_HP = 16
BOSS_P = 4

ALIENS = {
    "A": (["...XX...", "..XXXX..", ".XXXXXX.", "XX.XX.XX", "XXXXXXXX", "..X..X..", ".X.XX.X."],
          ["...XX...", "..XXXX..", ".XXXXXX.", "XX.XX.XX", "XXXXXXXX", ".X.XX.X.", "X.X..X.X"]),
    "B": (["..X..X..", "...XX...", "..XXXX..", ".XX..XX.", "XXXXXXXX", "X.XXXX.X", "X.X..X.X"],
          ["..X..X..", "X..XX..X", "X.XXXX.X", "XXX..XXX", "XXXXXXXX", "..XXXX..", ".X....X."]),
    "C": (["..XXXX..", ".XXXXXX.", "XXXXXXXX", "XX.XX.XX", "XXXXXXXX", ".XX..XX.", "XX....XX"],
          ["..XXXX..", ".XXXXXX.", "XXXXXXXX", "XX.XX.XX", "XXXXXXXX", "..XXXX..", ".XX..XX."]),
}
ROW_TYPES = ["A", "B", "B", "C", "C"]
BOOM = ["X..X..X.", ".X.X.X..", "..XXX..X", "XXX.XXX.", "..XXX...", ".X.X.X..", "X..X..X."]
SHIP = [".....X.....", "....XXX....", "....XXX....", ".XXXXXXXXX.", "XXXXXXXXXXX", "XXXXXXXXXXX", "XX..XXX..XX"]
BOSS = [
    "......XXXXXXXX......",
    "...XXXXXXXXXXXXXX...",
    "..XXXXXXXXXXXXXXXX..",
    ".XX..XX..XX..XX..XX.",
    "XXXXXXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXXXXXX",
    "..XXX..XXXXXX..XXX..",
    ".XX.....XXXX.....XX.",
    "XX.......XX.......XX",
    "X..................X",
]
BOSS_EYES = ["...XX..XX..XX..XX..."]
AW, AH = 8 * P, 7 * P
SW, SH = 11 * P, 7 * P
BW, BH = 20 * BOSS_P, 10 * BOSS_P

COLORS = {
    "bg": "#050B1A", "hud": "#A9C7E8", "value": "#EAF6FF", "accent": "#2EE6A6",
    "A": "#9B6CFF", "B": "#3FA9F5", "C": "#2EE6A6", "ship": "#EAF6FF", "shot": "#FFD166",
    "bomb": "#FF9F43", "boss": "#FF5C7A", "boss2": "#FFD166", "boom": "#FFD166", "shield": "#3FE0F5",
}


# ---------------------------------------------------------------- simulation

def lowest_per_column(aliens):
    low = {}
    for a in aliens:
        if a["alive"] and (a["col"] not in low or a["row"] > low[a["col"]]["row"]):
            low[a["col"]] = a
    return low


def simulate(seed, total):
    rng = random.Random(seed)
    aliens = [{"col": c, "row": r, "type": ROW_TYPES[r], "alive": True, "t_dead": None}
              for r in range(ROWS) for c in range(COLS)]
    fx, fy, dirx, step_timer = 60.0, 50.0, 1, 0.0
    t = 0.8
    ev = {
        "form": [(0.0, fx, fy)], "player": [(0.0, W / 2)], "shots": [], "bombs": [],
        "shield": [], "score": [(0.0, 0)], "boss": [], "boss_hits": [], "boss_shots": [], "booms": [],
    }
    px = W / 2
    bullets, bombs = [], []
    cooldown, bomb_timer, target = 0.0, 1.2, None
    alien_pts = round(total * 0.55)
    kills = 0

    def apos(a):
        return fx + a["col"] * CX, fy + a["row"] * CY

    def predict_fx(ahead, n_alive):
        x, d, timer, left_t = fx, dirx, step_timer, ahead
        cols = [a["col"] for a in aliens if a["alive"]]
        interval = 0.07 + 0.33 * n_alive / len(aliens)
        while left_t > 0:
            gap = interval - timer
            if gap > left_t:
                break
            left_t -= gap
            timer = 0.0
            lo, hi = x + min(cols) * CX, x + max(cols) * CX + AW
            if (d > 0 and hi + STEP > W - 16) or (d < 0 and lo - STEP < 16):
                d = -d
            else:
                x += d * STEP
        return x

    def move_player(tx):
        nonlocal px
        d = tx - px
        px += max(-PSPEED * DT, min(PSPEED * DT, d))
        px = max(SW / 2 + 8, min(W - SW / 2 - 8, px))
        ev["player"].append((t, px))

    def shield_hit(x, y):
        return px - SW / 2 - 6 <= x <= px + SW / 2 + 6 and PLAYER_Y - 6 <= y <= PLAYER_Y + SH

    # Phase 1: the alien formation.
    while any(a["alive"] for a in aliens) and t < 90:
        t += DT
        alive = [a for a in aliens if a["alive"]]
        step_timer += DT
        if step_timer >= 0.07 + 0.33 * len(alive) / len(aliens):
            step_timer = 0.0
            cols = [a["col"] for a in alive]
            left, right = fx + min(cols) * CX, fx + max(cols) * CX + AW
            if (dirx > 0 and right + STEP > W - 16) or (dirx < 0 and left - STEP < 16):
                dirx = -dirx
                if fy < FY_MAX:
                    fy += DOWN
            else:
                fx += dirx * STEP
            ev["form"].append((t, fx, fy))

        low = lowest_per_column(aliens)
        if target is None or not target["alive"]:
            target = min(low.values(), key=lambda a: abs(apos(a)[0] + AW / 2 - px))
        # Lead the shot: predict where the formation will be when the bullet arrives.
        travel = (PLAYER_Y - 8 - (apos(target)[1] + AH / 2)) / BSPEED
        tx = predict_fx(travel, len(alive)) + target["col"] * CX + AW / 2
        move_player(tx)

        cooldown -= DT
        if not bullets and cooldown <= 0 and abs(px - tx) < 4:
            bullets.append({"x": px, "y": PLAYER_Y - 8, "t0": t, "y0": PLAYER_Y - 8})
            cooldown = 0.2

        for b in bullets[:]:
            b["y"] -= BSPEED * DT
            hit = next((a for a in aliens if a["alive"]
                        and apos(a)[0] <= b["x"] <= apos(a)[0] + AW
                        and apos(a)[1] <= b["y"] <= apos(a)[1] + AH), None)
            if hit:
                hit["alive"], hit["t_dead"] = False, t
                kills += 1
                ev["score"].append((t, round(alien_pts * kills / len(aliens))))
                ev["shots"].append((b["t0"], t, b["x"], b["y0"], b["y"]))
                bullets.remove(b)
            elif b["y"] < HUD:
                ev["shots"].append((b["t0"], t, b["x"], b["y0"], b["y"]))
                bullets.remove(b)

        bomb_timer -= DT
        if bomb_timer <= 0:
            bomb_timer = rng.uniform(0.5, 1.3)
            options = [a for a in low.values() if abs(apos(a)[0] + AW / 2 - px) > 60]
            if options:
                a = rng.choice(options)
                x, y = apos(a)[0] + AW / 2, apos(a)[1] + AH
                bombs.append({"x": x, "y": y, "t0": t, "y0": y, "dx": 0.0, "vx": 0.0})
        for bm in bombs[:]:
            bm["y"] += BOMB_SPEED * DT
            if shield_hit(bm["x"], bm["y"]):
                ev["shield"].append(t)
                ev["bombs"].append((bm["t0"], t, bm["x"], bm["y0"], bm["x"], bm["y"]))
                bombs.remove(bm)
            elif bm["y"] > GROUND:
                ev["bombs"].append((bm["t0"], t, bm["x"], bm["y0"], bm["x"], bm["y"]))
                bombs.remove(bm)

    # Let anything still in the air finish.
    for b in bullets:
        ev["shots"].append((b["t0"], t, b["x"], b["y0"], b["y"]))
    for bm in bombs:
        ev["bombs"].append((bm["t0"], t, bm["x"], bm["y0"], bm["x"], bm["y"]))
    ev["aliens"] = aliens
    ev["aliens_done"] = t

    # Phase 2: WARNING, then the boss.
    ev["warn"] = (t + 0.5, t + 2.3)
    t += 2.3
    bx, by = W / 2 - BW / 2, -BH - 10.0
    entry_end = t + 1.2
    ev["boss"].append((t, bx, by))
    while t < entry_end:
        t += DT
        by = -BH - 10 + (56 + BH + 10) * min(1.0, 1 - (entry_end - t) / 1.2)
        ev["boss"].append((t, bx, by))
        move_player(bx + BW / 2)
    by = 56.0
    hp, waypoint, shot_timer = BOSS_HP, bx, 0.8
    bullets, boss_bullets = [], []
    cooldown = 0.0
    while hp > 0 and t < 200:
        t += DT
        if abs(waypoint - bx) < 2:
            waypoint = rng.uniform(20, W - 20 - BW)
        bx += max(-140 * DT, min(140 * DT, waypoint - bx))
        ev["boss"].append((t, bx, by))
        travel = (PLAYER_Y - 8 - (by + BH / 2)) / BSPEED
        center = bx + max(-140 * travel, min(140 * travel, waypoint - bx)) + BW / 2
        move_player(center)

        cooldown -= DT
        if len(bullets) < 2 and cooldown <= 0 and abs(px - center) < BW / 2 - 10:
            bullets.append({"x": px, "y": PLAYER_Y - 8, "t0": t, "y0": PLAYER_Y - 8})
            cooldown = 0.22
        for b in bullets[:]:
            b["y"] -= BSPEED * DT
            if bx <= b["x"] <= bx + BW and by <= b["y"] <= by + BH:
                hp -= 1
                ev["boss_hits"].append((t, b["x"] - bx, b["y"] - by))
                ev["score"].append((t, total if hp == 0 else alien_pts + round((total - alien_pts) * (BOSS_HP - hp) / BOSS_HP)))
                ev["shots"].append((b["t0"], t, b["x"], b["y0"], b["y"]))
                bullets.remove(b)
                if hp == 0:
                    break
            elif b["y"] < HUD:
                ev["shots"].append((b["t0"], t, b["x"], b["y0"], b["y"]))
                bullets.remove(b)

        shot_timer -= DT
        if shot_timer <= 0 and hp > 0:
            shot_timer = 1.0
            for vx in (-95, 0, 95):
                boss_bullets.append({"x": bx + BW / 2, "y": by + BH, "x0": bx + BW / 2, "y0": by + BH, "t0": t, "vx": vx})
        for bb in boss_bullets[:]:
            bb["x"] += bb["vx"] * DT
            bb["y"] += 210 * DT
            if shield_hit(bb["x"], bb["y"]):
                ev["shield"].append(t)
            if shield_hit(bb["x"], bb["y"]) or bb["y"] > GROUND or not 0 < bb["x"] < W:
                ev["boss_shots"].append((bb["t0"], t, bb["x0"], bb["y0"], bb["x"], bb["y"]))
                boss_bullets.remove(bb)

    for bb in boss_bullets:
        ev["boss_shots"].append((bb["t0"], t, bb["x0"], bb["y0"], bb["x"], bb["y"]))
    for b in bullets:
        ev["shots"].append((b["t0"], t, b["x"], b["y0"], b["y"]))

    t_death = t
    for i in range(9):
        ev["booms"].append((t_death + i * 0.11, bx + rng.uniform(0, BW - 24), by + rng.uniform(0, BH - 21)))
    ev["boss_gone"] = t_death + 0.6
    ev["clear"] = t_death + 1.3
    ev["end"] = ev["clear"] + 3.2
    return ev


# ---------------------------------------------------------------- rendering

def sprite_path(rows, size, ox=0, oy=0):
    parts = []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "X":
                parts.append(f"M{ox + x * size} {oy + y * size}h{size}v{size}h-{size}z")
    return "".join(parts)


def compress(points):
    """Drop samples that lie on a straight line between their neighbours."""
    if len(points) < 3:
        return points
    out = [points[0]]
    for prev, cur, nxt in zip(points, points[1:], points[2:]):
        dt1, dt2 = cur[0] - prev[0], nxt[0] - cur[0]
        slope1 = [(c - p) / dt1 for p, c in zip(prev[1:], cur[1:])] if dt1 else None
        slope2 = [(n - c) / dt2 for c, n in zip(cur[1:], nxt[1:])] if dt2 else None
        if slope1 is None or slope2 is None or any(abs(a - b) > 1e-6 for a, b in zip(slope1, slope2)):
            out.append(cur)
    out.append(points[-1])
    return out


def render(ev):
    cycle = ev["end"]
    pct = lambda s: f"{min(max(s / cycle * 100, 0), 100):.4f}%"
    css = [
        "text{font-family:'Fira Code','Consolas',monospace;font-weight:700}",
        ".st{animation-timing-function:step-end!important}",
        ".ln{animation-timing-function:linear!important}",
        "@keyframes fa{0%{opacity:1}50%{opacity:0}}@keyframes fb{0%{opacity:0}50%{opacity:1}}",
        ".fa{animation:fa 1s step-end infinite}.fb{animation:fb 1s step-end infinite;opacity:0}",
        "@keyframes tw{50%{opacity:.15}}.tw{animation:tw 2.6s ease-in-out infinite}",
    ]
    out = [f'<rect width="{W}" height="{H}" rx="12" fill="{COLORS["bg"]}"/>']
    anim = lambda name, frames, kind="st": css.append(
        f"@keyframes {name}{{{frames}}}.{name}{{animation:{name} {cycle:.3f}s infinite}}")

    # Starfield.
    rng = random.Random(7)
    stars = "".join(
        f'<circle class="tw" cx="{rng.uniform(8, W - 8):.0f}" cy="{rng.uniform(HUD, GROUND - 10):.0f}" '
        f'r="{rng.choice((0.8, 1.0, 1.3))}" style="animation-delay:{rng.uniform(0, 2.6):.1f}s"/>'
        for _ in range(45))
    out.append(f'<g fill="#EAF6FF" opacity=".55">{stars}</g>')
    out.append(f'<rect x="12" y="{GROUND}" width="{W - 24}" height="2" fill="{COLORS["accent"]}" opacity=".5"/>')

    # Alien formation.
    frames = "".join(f"{pct(tm)}{{transform:translate({x:.0f}px,{y:.0f}px)}}" for tm, x, y in ev["form"])
    anim("form", frames)
    inner = []
    for i, a in enumerate(ev["aliens"]):
        ax, ay = a["col"] * CX, a["row"] * CY
        f1, f2 = ALIENS[a["type"]]
        t_dead = a["t_dead"] if a["t_dead"] is not None else ev["aliens_done"]
        anim(f"al{i}", f"0%{{opacity:1}}{pct(t_dead)}{{opacity:0}}100%{{opacity:0}}")
        inner.append(f'<g class="al{i} st" fill="{COLORS[a["type"]]}">'
                     f'<path class="fa" d="{sprite_path(f1, P, ax, ay)}"/>'
                     f'<path class="fb" d="{sprite_path(f2, P, ax, ay)}"/></g>')
        anim(f"ex{i}", f"0%{{opacity:0}}{pct(t_dead)}{{opacity:1}}{pct(t_dead + 0.22)}{{opacity:0}}100%{{opacity:0}}")
        inner.append(f'<path class="ex{i} st" style="opacity:0" fill="{COLORS["boom"]}" d="{sprite_path(BOOM, P, ax, ay)}"/>')
    out.append(f'<g class="form st">{"".join(inner)}</g>')

    # Player shots.
    for i, (t0, t1, x, y0, y1) in enumerate(ev["shots"]):
        anim(f"s{i}", f"0%,{pct(t0 - EPS)}{{opacity:0;transform:translateY(0px)}}{pct(t0)}{{opacity:1;transform:translateY(0px)}}"
                      f"{pct(t1)}{{opacity:1;transform:translateY({y1 - y0:.1f}px)}}{pct(t1 + EPS)},100%{{opacity:0;transform:translateY({y1 - y0:.1f}px)}}")
        out.append(f'<rect class="s{i} ln" style="opacity:0" x="{x - 1:.1f}" y="{y0 - 8:.1f}" width="3" height="9" rx="1" fill="{COLORS["shot"]}"/>')

    # Alien bombs and boss bullets.
    for name, items, color, size in (("b", ev["bombs"], COLORS["bomb"], (3, 8)), ("q", ev["boss_shots"], COLORS["boss"], (6, 6))):
        for i, (t0, t1, x0, y0, x1, y1) in enumerate(items):
            dx, dy = x1 - x0, y1 - y0
            anim(f"{name}{i}", f"0%,{pct(t0 - EPS)}{{opacity:0;transform:translate(0px,0px)}}{pct(t0)}{{opacity:1;transform:translate(0px,0px)}}"
                               f"{pct(t1)}{{opacity:1;transform:translate({dx:.1f}px,{dy:.1f}px)}}{pct(t1 + EPS)},100%{{opacity:0;transform:translate({dx:.1f}px,{dy:.1f}px)}}")
            w, h = size
            out.append(f'<rect class="{name}{i} ln" style="opacity:0" x="{x0 - w / 2:.1f}" y="{y0:.1f}" width="{w}" height="{h}" rx="{w / 2}" fill="{color}"/>')

    # Boss: visibility, movement, hit flashes and HP bar.
    t_in = ev["boss"][0][0]
    anim("bv", f"0%{{opacity:0}}{pct(t_in)}{{opacity:1}}{pct(ev['boss_gone'])}{{opacity:0}}100%{{opacity:0}}")
    pts = compress(ev["boss"])
    anim("bm", "".join(f"{pct(tm)}{{transform:translate({x:.1f}px,{y:.1f}px)}}" for tm, x, y in pts))
    flash = "0%{opacity:0}" + "".join(f"{pct(tm)}{{opacity:.85}}{pct(tm + 0.07)}{{opacity:0}}" for tm, _, _ in ev["boss_hits"]) + "100%{opacity:0}"
    anim("bf", flash)
    sparks = []
    for i, (tm, hx, hy) in enumerate(ev["boss_hits"]):
        anim(f"k{i}", f"0%{{opacity:0}}{pct(tm)}{{opacity:1}}{pct(tm + 0.12)}{{opacity:0}}100%{{opacity:0}}")
        sparks.append(f'<circle class="k{i} st" style="opacity:0" cx="{hx:.1f}" cy="{hy:.1f}" r="5" fill="{COLORS["boss2"]}"/>')
    boss = sprite_path(BOSS, BOSS_P)
    out.append(f'<g class="bv st" style="opacity:0"><g class="bm ln">'
               f'<path d="{boss}" fill="{COLORS["boss"]}"/>'
               f'<path d="{sprite_path(BOSS_EYES, BOSS_P, 0, 3 * BOSS_P)}" fill="{COLORS["boss2"]}"/>'
               f'<path class="bf st" style="opacity:0" d="{boss}" fill="#FFFFFF"/>{"".join(sparks)}</g></g>')

    hp_frames = f"0%{{transform:scaleX(1)}}" + "".join(
        f"{pct(tm)}{{transform:scaleX({(BOSS_HP - i - 1) / BOSS_HP:.4f})}}" for i, (tm, _, _) in enumerate(ev["boss_hits"]))
    anim("hp", hp_frames + "100%{transform:scaleX(0)}")
    hx = W / 2 - 120
    out.append(f'<g class="bv st" style="opacity:0">'
               f'<text x="{hx}" y="{HUD + 10}" font-size="9" fill="{COLORS["boss"]}">BOSS</text>'
               f'<rect x="{hx + 34}" y="{HUD + 3}" width="206" height="7" rx="3" fill="#1C2A44"/>'
               f'<rect class="hp st" x="{hx + 34}" y="{HUD + 3}" width="206" height="7" rx="3" fill="{COLORS["boss"]}" '
               f'style="transform-origin:{hx + 34}px {HUD + 6}px;transform-box:view-box"/></g>')

    for i, (tm, x, y) in enumerate(ev["booms"]):
        anim(f"x{i}", f"0%{{opacity:0}}{pct(tm)}{{opacity:1}}{pct(tm + 0.3)}{{opacity:0}}100%{{opacity:0}}")
        out.append(f'<path class="x{i} st" style="opacity:0" fill="{COLORS["boom"] if i % 2 else COLORS["boss2"]}" d="{sprite_path(BOOM, 4, round(x), round(y))}"/>')

    # Player ship with shield flashes.
    pts = compress(ev["player"])
    anim("pl", "".join(f"{pct(tm)}{{transform:translateX({x - SW / 2:.1f}px)}}" for tm, x in pts))
    shield = "0%{opacity:0}" + "".join(f"{pct(tm)}{{opacity:.9}}{pct(tm + 0.18)}{{opacity:0}}" for tm in ev["shield"]) + "100%{opacity:0}"
    anim("sh", shield)
    out.append(f'<g class="pl ln"><path d="{sprite_path(SHIP, P, 0, PLAYER_Y)}" fill="{COLORS["ship"]}"/>'
               f'<rect x="{4 * P}" y="{PLAYER_Y + 3 * P}" width="{3 * P}" height="{P}" fill="{COLORS["accent"]}"/>'
               f'<ellipse class="sh st" style="opacity:0" cx="{SW / 2}" cy="{PLAYER_Y + SH / 2}" rx="{SW / 2 + 7}" ry="{SH / 2 + 8}" '
               f'fill="none" stroke="{COLORS["shield"]}" stroke-width="2"/></g>')

    # HUD.
    out.append(f'<text x="18" y="20" font-size="10" fill="{COLORS["hud"]}">SCORE</text>')
    states = ev["score"]
    for k, (tm, score) in enumerate(states):
        end = states[k + 1][0] if k + 1 < len(states) else cycle
        anim(f"sc{k}", f"0%{{opacity:{1 if k == 0 else 0}}}{pct(tm)}{{opacity:1}}{pct(end)}{{opacity:0}}100%{{opacity:{1 if k == 0 else 0}}}")
        out.append(f'<text class="sc{k} st" style="opacity:{1 if k == 0 else 0}" x="62" y="20" font-size="13" fill="{COLORS["value"]}">{score:,}</text>')
    out.append(f'<text x="{W / 2}" y="20" font-size="11" fill="{COLORS["accent"]}" text-anchor="middle">CONTRIBUTION INVADERS</text>')
    out.append(f'<text x="{W - 18}" y="20" font-size="11" fill="{COLORS["accent"]}" text-anchor="end">by {AUTHOR}</text>')
    out.append(f'<text x="18" y="{H - 4}" font-size="8" fill="{COLORS["hud"]}" opacity=".7">score = contributions</text>')

    w0, w1 = ev["warn"]
    blink = "0%{opacity:0}" + "".join(
        f"{pct(w0 + i * 0.3)}{{opacity:{1 if i % 2 == 0 else 0}}}" for i in range(int((w1 - w0) / 0.3))) + f"{pct(w1)}{{opacity:0}}100%{{opacity:0}}"
    anim("wn", blink)
    out.append(f'<text class="wn st" style="opacity:0" x="{W / 2}" y="{H / 2}" font-size="34" fill="{COLORS["boss"]}" text-anchor="middle" letter-spacing="6">WARNING</text>')
    anim("cl", f"0%{{opacity:0}}{pct(ev['clear'])}{{opacity:1}}{pct(cycle - 0.3)}{{opacity:0}}100%{{opacity:0}}")
    out.append(f'<g class="cl st" style="opacity:0"><text x="{W / 2}" y="{H / 2 - 6}" font-size="30" fill="{COLORS["accent"]}" text-anchor="middle" letter-spacing="4">STAGE CLEAR</text>'
               f'<text x="{W / 2}" y="{H / 2 + 22}" font-size="13" fill="{COLORS["value"]}" text-anchor="middle">SCORE {ev["score"][-1][1]:,}</text></g>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" data-author="JuhaP2" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            f"<style>{''.join(css)}</style>{''.join(out)}</svg>")


def main():
    user, out_dir = sys.argv[1], sys.argv[2]
    total = fetch_total(user, os.environ["GITHUB_TOKEN"])
    ev = simulate(total * 1000 + datetime.date.today().toordinal(), total)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "invaders.svg"), "w", encoding="utf-8") as f:
        f.write(render(ev))
    print(f"{user}: {total} contributions, {len(ev['shots'])} shots, {ev['end']:.1f}s loop")


if __name__ == "__main__":
    main()
