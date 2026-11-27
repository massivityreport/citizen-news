#!/usr/bin/env python3
"""Vérification de bout en bout de l'API Citizen News V2 (bibliothèque standard seule, aucune dépendance).

    python3 scripts/smoke.py [--base http://localhost:8000] [--radar-max 3]
    ADMIN_PASSWORD=… python3 scripts/smoke.py          # ajoute la partie admin

--base       l'API (http://localhost:8000, publié par docker compose en local) ou le front nginx qui la proxifie
             (http://localhost:8080). Ne vérifie PAS le front lui-même.
--radar-max  valeur de RADAR_MAX_SOURCES de l'API (défaut 3).
ADMIN_PASSWORD (variable d'environnement, jamais en argument) : sans elle, la partie admin est sautée (dit).

Ce que le script vérifie, dans l'ordre :
  Public  : GET /api/health ; GET /api/topics/pool (3 onglets : random avec graine stable, recent, radar ; 422 sans
            graine ; cartes complètes, image_url null ou https ; AUCUN compteur ni classement dans le bassin) ;
            GET /api/edition/current ; GET /api/editions ; GET /api/editions/{date} (200 pour une édition existante,
            404 pour une date sans édition, 422 pour une date mal formée) ; édition publiée = classement figé.
  Anonyme : 401 sur /api/me, /api/me/une et /api/admin/edition/preview ; POST /api/auth/magic-link avec un brouillon
            de une : 202 (identique sans brouillon), 422 pour un e-mail mal formé.
  Admin (si ADMIN_PASSWORD) : mauvais mot de passe 401 ; login ; /api/admin/edition/preview, /editions, /stats et
            /topics (formes, tri par approbations, aucune adresse e-mail dans les réponses) ; logout puis 401.
Un bassin ou un historique vide n'est pas une erreur du code mais un état de la base : le script le dit
(« lancez seed-demo ») et saute les contrôles qui en dépendent.

Sort 0 si tout passe, 1 au premier écart (« ÉCART : … »). N'écrit rien dans la base, sauf un jeton de lien
magique (une demande, e-mail smoke-<horodatage>@example.org ; avec MAIL_BACKEND=console, aucun e-mail réel) : ne
pas boucler plus de quelques fois par heure (limites de débit).
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

FORBIDDEN_KEYS = re.compile(r"approval|score|vote|support|reason|rank|proportion|participant", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
CARD_KEYS = {"id", "title", "summary", "sources", "article_count", "source_count", "first_seen_at", "updated_at", "image_url"}


class Gap(Exception):
    pass


def ok(msg: str) -> None:
    print(f"  ok  {msg}")


def note(msg: str) -> None:
    print(f"  --  {msg}")


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise Gap(msg)
    ok(msg)


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.cookie: str | None = None

    def call(self, method: str, path: str, body=None, expect: int | None = None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.cookie:
            headers["Cookie"] = self.cookie
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as e:
            resp = e
        raw = resp.read()
        for sc in resp.headers.get_all("Set-Cookie") or []:
            pair = sc.split(";", 1)[0]
            self.cookie = None if pair.split("=", 1)[1] == "" else pair
        try:
            payload = json.loads(raw) if raw and "json" in (resp.headers.get("Content-Type") or "") else raw
        except ValueError:
            payload = raw
        if expect is not None and resp.status != expect:
            raise Gap(f"{method} {path} : attendu {expect}, obtenu {resp.status} ({str(payload)[:200]})")
        return resp, payload


def keys_anywhere(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys_anywhere(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys_anywhere(v)}
    return set()


def check_card(card: dict, where: str) -> None:
    check(
        CARD_KEYS <= set(card) and card["source_count"] >= 2 and len(card["sources"]) >= 1
        and (card["image_url"] is None or str(card["image_url"]).startswith("https://")),
        f"{where} : carte complète (id, title, summary, sources, compteurs de médias, dates, image_url null ou https)",
    )


def public(c: Client, radar_max: int) -> list[int]:
    print("Public")
    _, h = c.call("GET", "/api/health", expect=200)
    check(h == {"status": "ok"}, "GET /api/health")

    seed = f"smoke-{int(time.time())}-seed"
    r, pool = c.call("GET", f"/api/topics/pool?tab=random&seed={seed}", expect=200)
    check("no-store" in (r.headers.get("Cache-Control") or ""), "bassin : Cache-Control no-store")
    check(
        {"edition_date", "closes_at", "open", "total", "items"} <= set(pool) and isinstance(pool["open"], bool),
        f"GET /api/topics/pool?tab=random : edition_date {pool.get('edition_date')}, open {pool.get('open')}, total {pool.get('total')}",
    )
    items = pool["items"]
    bad = {k for k in keys_anywhere(pool) if FORBIDDEN_KEYS.search(k)}
    check(not bad, "le bassin ne contient aucun compteur d'approbation, score, classement ni vote (clés suspectes : " + (", ".join(sorted(bad)) or "aucune") + ")")
    c.call("GET", "/api/topics/pool?tab=random", expect=422)
    ok("onglet random sans graine : 422")
    c.call("GET", "/api/topics/pool?tab=inconnu&seed=" + seed, expect=422)
    ok("onglet inconnu : 422")
    _, recent = c.call("GET", "/api/topics/pool?tab=recent", expect=200)
    _, radar = c.call("GET", "/api/topics/pool?tab=radar", expect=200)
    ok(f"3 onglets joignables : random {len(items)} / recent {len(recent['items'])} / radar {len(radar['items'])} sujet(s)")
    if not items:
        note("bassin vide : lancez `python -m app.cli seed-demo` (DEMO_SEED=true) ou refresh ; contrôles de cartes sautés")
        ids: list[int] = []
    else:
        check_card(items[0], f"carte #{items[0]['id']}")
        _, again = c.call("GET", f"/api/topics/pool?tab=random&seed={seed}", expect=200)
        check([i["id"] for i in again["items"]] == [i["id"] for i in items], "random : même graine, même ordre")
        check({i["id"] for i in items} == {i["id"] for i in recent["items"]}, "random et recent listent les mêmes sujets")
        check([i["updated_at"] for i in recent["items"]] == sorted((i["updated_at"] for i in recent["items"]), reverse=True), "recent : du plus récent au plus ancien")
        check(all(i["source_count"] <= radar_max for i in radar["items"]), f"radar : au plus {radar_max} média(s) par sujet")
        check(
            {i["id"] for i in radar["items"]} == {i["id"] for i in recent["items"] if i["source_count"] <= radar_max},
            "radar = les sujets du bassin peu couverts",
        )
        ids = [i["id"] for i in items]

    _, cur = c.call("GET", "/api/edition/current", expect=200)
    check({"edition", "next_close_at", "server_time"} <= set(cur), "GET /api/edition/current : edition, next_close_at, server_time")
    check(cur["next_close_at"] > cur["server_time"], f"la prochaine clôture ({cur['next_close_at']}) est dans le futur")

    _, listing = c.call("GET", "/api/editions?limit=30", expect=200)
    editions = listing["items"]
    check(all({"date", "published_at", "participants", "topic_count"} <= set(e) for e in editions), f"GET /api/editions : {len(editions)} édition(s)")
    check([e["date"] for e in editions] == sorted((e["date"] for e in editions), reverse=True), "éditions : plus récentes d'abord")
    c.call("GET", "/api/editions?limit=0", expect=422)
    ok("limit=0 : 422")
    if editions:
        day = editions[0]["date"]
        _, ed = c.call("GET", f"/api/editions/{day}", expect=200)
        topics = ed["topics"]
        check(ed["date"] == day and len(topics) == editions[0]["topic_count"], f"GET /api/editions/{day} : {len(topics)} sujet(s), permalien stable")
        check([t["rank"] for t in topics] == list(range(1, len(topics) + 1)), "l'édition publiée est classée 1..n")
        check(all(0 <= t["approvals"] <= ed["participants"] for t in topics), "approbations ≤ participants (compteurs permis ici : édition publiée)")
        if cur["edition"]:
            check(cur["edition"]["date"] == editions[0]["date"], "edition/current = la plus récente des éditions")
    else:
        note("aucune édition publiée : lancez seed-demo ; permalien existant non vérifié")
    c.call("GET", "/api/editions/2000-01-01", expect=404)
    ok("date sans édition : 404")
    c.call("GET", "/api/editions/pas-une-date", expect=422)
    ok("date mal formée : 422")
    return ids


def anonymous(c: Client, topic_ids: list[int]) -> None:
    print("Anonyme")
    for path in ("/api/me", "/api/me/une", "/api/admin/edition/preview", "/api/admin/stats"):
        c.call("GET", path, expect=401)
        ok(f"GET {path} sans session : 401")
    c.call("PUT", "/api/me/une", {"topic_ids": topic_ids[:1]}, expect=401)
    ok("PUT /api/me/une sans session : 401")
    c.call("POST", "/api/auth/verify", {"token": "invalide"}, expect=400)
    ok("verify avec un jeton invalide : 400")
    c.call("POST", "/api/auth/magic-link", {"email": "pas-un-email"}, expect=422)
    ok("magic-link avec un e-mail mal formé : 422")
    email = f"smoke-{int(time.time())}@example.org"
    _, body = c.call("POST", "/api/auth/magic-link", {"email": email, "draft": {"topic_ids": topic_ids[:3]}}, expect=202)
    check(body == {}, f"POST /api/auth/magic-link avec un brouillon de {len(topic_ids[:3])} sujet(s) : 202, corps vide")
    c.call("POST", "/api/auth/magic-link", {"email": email, "draft": {"topic_ids": list(range(1, 12))}}, expect=422)
    ok("brouillon de plus de 10 sujets : 422")


def admin(base: str, password: str) -> None:
    print("Admin")
    a = Client(base)
    a.call("POST", "/api/admin/login", {"password": "mauvais-" + password}, expect=401)
    ok("login avec un mauvais mot de passe : 401")
    r, _ = a.call("POST", "/api/admin/login", {"password": password}, expect=200)
    cookie = r.headers.get("Set-Cookie", "").lower()
    check("httponly" in cookie and "path=/api/admin" in cookie, "login : cookie cn_admin httpOnly, Path=/api/admin")
    _, pv = a.call("GET", "/api/admin/edition/preview", expect=200)
    check(
        {"computed_at", "edition_date", "participants", "topics", "next", "ties"} <= set(pv) and len(pv["topics"]) <= 10,
        f"aperçu de l'édition {pv['edition_date']} : {pv['participants']} participant(s), {len(pv['topics'])} dans la une, {len(pv['next'])} suivants, {len(pv['ties'])} égalité(s)",
    )
    ranked = pv["topics"] + pv["next"]
    check([t["rank"] for t in ranked] == list(range(1, len(ranked) + 1)), "aperçu : rangs consécutifs")
    check([t["approvals"] for t in ranked] == sorted((t["approvals"] for t in ranked), reverse=True), "aperçu : trié par approbations")
    if any(t["crosses_cut"] for t in pv["ties"]):
        note("une égalité chevauche la coupure 10/11 (visible dans l'aperçu)")
    _, eds = a.call("GET", "/api/admin/editions", expect=200)
    check({"items", "total", "page", "page_size"} <= set(eds), f"GET /api/admin/editions : {eds['total']} édition(s)")
    if eds["items"]:
        a.call("GET", f"/api/admin/editions/{eds['items'][0]['date']}", expect=200)
        ok("GET /api/admin/editions/{date} : 200")
    a.call("GET", "/api/admin/editions/2000-01-01", expect=404)
    ok("édition admin inconnue : 404")
    _, stats = a.call("GET", "/api/admin/stats", expect=200)
    check(len(stats["series"]) == 30 and {"last_24h", "total"} <= set(stats), "GET /api/admin/stats : last_24h, total, série de 30 jours")
    _, tp = a.call("GET", "/api/admin/topics?page_size=20", expect=200)
    check({"items", "total", "page", "page_size"} <= set(tp), f"GET /api/admin/topics : {tp['total']} sujet(s)")
    check([t["approvals"] for t in tp["items"]] == sorted((t["approvals"] for t in tp["items"]), reverse=True), "sujets admin : tri par approbations par défaut")
    emails = {m for payload in (pv, eds, stats, tp) for m in EMAIL_RE.findall(json.dumps(payload))}
    check(not emails, "aucune adresse e-mail dans les réponses admin")
    a.call("POST", "/api/admin/logout", expect=204)
    a.call("GET", "/api/admin/edition/preview", expect=401)
    ok("après logout : 401")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--radar-max", type=int, default=3)
    args = ap.parse_args()
    password = os.environ.get("ADMIN_PASSWORD", "")
    try:
        ids = public(Client(args.base), args.radar_max)
        anonymous(Client(args.base), ids)
        if password:
            admin(args.base, password)
        else:
            print("Admin\n  --  ADMIN_PASSWORD absent de l'environnement : partie admin sautée (login, aperçu, éditions, stats, sujets)")
    except Gap as e:
        print(f"\nÉCART : {e}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError) as e:
        print(f"\nÉCART : service injoignable : {e}", file=sys.stderr)
        return 1
    print("\nParcours complet : OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
