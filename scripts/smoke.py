#!/usr/bin/env python3
"""Parcours de bout en bout de l'API (bibliothèque standard seule, aucune dépendance).

    python3 scripts/smoke.py [--base http://localhost:8080] [--mailpit http://localhost:8025] [--logs]

--base     le front (nginx, proxifie /api) ou directement l'API (http://localhost:8000).
--mailpit  récupère le lien magique dans mailpit (profil `mail`, MAIL_BACKEND=smtp).
--api-only ne vérifie pas le front (GET / HTML, repli SPA) : pour --base http://localhost:8000.
--logs     sinon : le lit dans `docker compose logs api` (MAIL_BACKEND=console, développement).
Sort 0 si tout passe, 1 au premier écart (message « ÉCART : … »). Crée un compte jetable
smoke-<horodatage>@example.org ; ne supprime rien. Consomme 1 lien magique et quelques votes sur les
limites de débit : à ne pas boucler plus de quelques fois par heure.
"""
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_RE = re.compile(r"/connexion\?token=([A-Za-z0-9_\-]+)")


class Gap(Exception):
    pass


def ok(msg: str) -> None:
    print(f"  ok  {msg}")


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
            if pair.split("=", 1)[1] == "":
                self.cookie = None
            else:
                self.cookie = pair
        try:
            payload = json.loads(raw) if raw and "json" in (resp.headers.get("Content-Type") or "") else raw
        except ValueError:
            payload = raw
        if expect is not None and resp.status != expect:
            raise Gap(f"{method} {path} : attendu {expect}, obtenu {resp.status} ({str(payload)[:200]})")
        return resp, payload


def link_from_mailpit(mailpit: str, email: str) -> str:
    base = mailpit.rstrip("/")
    for _ in range(30):
        with urllib.request.urlopen(f"{base}/api/v1/search?query=" + urllib.parse.quote(f"to:{email}"), timeout=10) as r:
            found = json.load(r).get("messages", [])
        if found:
            with urllib.request.urlopen(f"{base}/api/v1/message/{found[0]['ID']}", timeout=10) as r:
                return json.load(r)["Text"]
        time.sleep(1)
    raise Gap(f"aucun e-mail pour {email} dans mailpit après 30 s")


def link_from_logs(email: str) -> str:
    for _ in range(30):
        out = subprocess.run(["docker", "compose", "logs", "--no-log-prefix", "api"], capture_output=True, text=True).stdout
        parts = out.split("To: " + email)
        if len(parts) > 1:
            return parts[-1]
        time.sleep(1)
    raise Gap(f"aucun lien pour {email} dans `docker compose logs api` après 30 s")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--mailpit", default=None)
    ap.add_argument("--logs", action="store_true")
    ap.add_argument("--api-only", action="store_true", help="ne vérifie pas le front")
    args = ap.parse_args()
    if not args.mailpit and not args.logs:
        ap.error("indiquez --mailpit <url> ou --logs pour récupérer le lien magique")

    c = Client(args.base)
    email = f"smoke-{int(time.time())}@example.org"
    try:
        print("Public")
        _, h = c.call("GET", "/api/health", expect=200)
        check(h == {"status": "ok"}, "GET /api/health")
        if args.api_only:
            print("  --  --api-only : front non vérifié")
        else:
            r, page = c.call("GET", "/", expect=200)
            check("html" in (r.headers.get("Content-Type") or "") and b'<div id="root"' in page, "GET / sert le front (nginx) ; sinon utilisez --api-only")
            r2, _ = c.call("GET", "/connexion", expect=200)
            check("html" in r2.headers.get("Content-Type", ""), "GET /connexion : repli SPA")
            check(r.headers.get("Referrer-Policy") == "no-referrer", "Referrer-Policy: no-referrer")
        _, front = c.call("GET", "/api/topics/front?limit=5", expect=200)
        items = front["items"]
        check(len(items) > 0, f"la une contient {len(items)} sujet(s) (lancez refresh / seed-demo sinon)")
        first = items[0]
        check(
            {"id", "title", "support", "reason", "sources"} <= set(first) and first["support"]["level"] in ("low", "medium", "high"),
            f"carte de la une #{first['id']} : id, title, sources, support, reason",
        )
        check(isinstance(front.get("has_more"), bool), f"la une expose has_more ({front.get('has_more')})")
        _, dflt = c.call("GET", "/api/topics/front", expect=200)
        check(len(dflt["items"]) <= 10, f"la une : {len(dflt['items'])} sujet(s) par défaut (10 au plus)")
        _, nxt = c.call("GET", "/api/vote/next?count=5", expect=200)
        cards = nxt["items"]
        check(len(cards) > 0, f"vote/next renvoie {len(cards)} sujet(s)")
        check(all("support" not in k and "reason" not in k for k in cards), "vote/next masque support et reason")
        _, cfg = c.call("GET", "/api/halving/config", expect=200)
        check(set(cfg["params"]) == set(cfg["description"]) and "keep_ratio" in cfg["params"], "GET /api/halving/config")

        print("Anonyme")
        c.call("GET", "/api/me", expect=401)
        ok("GET /api/me sans session : 401")
        c.call("POST", "/api/votes", {"topic_id": cards[0]["id"], "choice": "more"}, expect=401)
        ok("POST /api/votes sans session : 401")
        _, _ = c.call("POST", "/api/auth/verify", {"token": "invalide"}, expect=400)
        ok("verify avec un jeton invalide : 400")
        c.call("POST", "/api/auth/magic-link", {"email": "pas-un-email"}, expect=422)
        ok("magic-link avec un e-mail mal formé : 422")

        print("Connexion par lien magique")
        c.call("POST", "/api/auth/magic-link", {"email": email}, expect=202)
        ok(f"POST /api/auth/magic-link {email} : 202")
        text = link_from_mailpit(args.mailpit, email) if args.mailpit else link_from_logs(email)
        m = TOKEN_RE.search(text)
        check(m is not None, "le message contient {APP_BASE_URL}/connexion?token=…")
        link = re.search(r"https?://\S*/connexion\?token=", text)
        check(link is not None, "le lien est une URL absolue …/connexion?token=")
        print(f"      lien : {link.group(0)}…")
        r, me = c.call("POST", "/api/auth/verify", {"token": m.group(1)}, expect=200)
        check(me == {"email": email}, "POST /api/auth/verify : 200 {email}")
        set_cookie = r.headers.get("Set-Cookie", "")
        check("httponly" in set_cookie.lower() and "samesite=lax" in set_cookie.lower(), f"cookie de session httpOnly SameSite=Lax ({set_cookie.split(';')[0].split('=')[0]})")
        c.call("POST", "/api/auth/verify", {"token": m.group(1)}, expect=400)
        ok("le lien est à usage unique (2e verify : 400)")
        _, me = c.call("GET", "/api/me", expect=200)
        check(me == {"email": email}, "GET /api/me avec le cookie")

        print("Votes")
        distinct = list(dict.fromkeys([x["id"] for x in cards] + [x["id"] for x in items]))
        check(len(distinct) >= 3, "au moins 3 sujets distincts pour tester les votes (lancez refresh / seed-demo)")
        a = distinct[0]
        extra = set(distinct[1:3])
        _, claimed = c.call("POST", "/api/votes/claim", {"votes": [{"topic_id": a, "choice": "more"}, {"topic_id": 999999999, "choice": "more"}]}, expect=200)
        check(claimed == {"claimed": 1}, "claim : 1 rattaché, sujet inconnu ignoré")
        _, again = c.call("POST", "/api/votes/claim", {"votes": [{"topic_id": a, "choice": "not_priority"}]}, expect=200)
        check(again == {"claimed": 0}, "claim n'écrase pas un vote existant")
        _, v = c.call("POST", "/api/votes", {"topic_id": a, "choice": "not_priority"}, expect=200)
        check(v == {"topic_id": a, "choice": "not_priority"}, "vote connecté remplace le vote")
        for t in extra:
            c.call("POST", "/api/votes", {"topic_id": t, "choice": "unknown"}, expect=200)
        _, mine = c.call("GET", "/api/votes/mine", expect=200)
        got = {x["topic_id"]: x["choice"] for x in mine["votes"]}
        check(got.get(a) == "not_priority" and all(got.get(t) == "unknown" for t in extra), "GET /api/votes/mine reflète les votes")
        c.call("POST", "/api/votes", {"topic_id": a, "choice": "peut-etre"}, expect=422)
        ok("choix invalide : 422")
        c.call("POST", "/api/votes", {"topic_id": 999999999, "choice": "more"}, expect=404)
        ok("sujet inconnu : 404")
        _, nxt2 = c.call("GET", "/api/vote/next?count=20", expect=200)
        check(a not in {x["id"] for x in nxt2["items"]}, "vote/next exclut les sujets déjà votés (session présente)")

        print("Déconnexion")
        c.call("POST", "/api/auth/logout", expect=204)
        c.call("GET", "/api/me", expect=401)
        ok("après logout : /api/me 401")
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
