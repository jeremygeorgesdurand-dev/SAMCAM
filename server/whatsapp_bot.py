"""
SAMCAM — Bot WhatsApp (WhatsApp Business Cloud API, Meta).

Le bot est une simple FAÇADE sur l'API SAMCAM déjà existante : il ne
recalcule jamais rien lui-même, il traduit un message WhatsApp en appel à
/api/risk, /api/assistant ou /api/signalement, puis reformate la réponse
en texte WhatsApp. Monté comme routeur FastAPI dans server/api.py, il
profite donc automatiquement de la publication Tailscale Funnel déjà en
place (Meta a besoin d'un webhook HTTPS public pour livrer les messages).

Configuration requise (variables d'environnement) — voir
docs/RAPPORT_SAMCAM.md §10.2 pour la procédure de création du compte Meta :
    WHATSAPP_VERIFY_TOKEN   — chaîne arbitraire choisie par vous, à
                              recopier dans la console Meta lors de la
                              configuration du webhook
    WHATSAPP_ACCESS_TOKEN   — jeton d'accès de l'app WhatsApp Business
    WHATSAPP_PHONE_NUMBER_ID — identifiant du numéro expéditeur (console Meta)

Sans ces variables, le routeur reste monté mais répond 503 : le reste du
serveur (app mobile, dashboard) n'est jamais affecté par leur absence.
"""

import json
import os
import re
import unicodedata
from typing import Optional

import httpx
from fastapi import APIRouter, Query, Request, Response

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# L'API SAMCAM tourne dans le MÊME processus (api.py monte ce routeur) ;
# on l'appelle par HTTP local plutôt que par import direct pour rester
# découplé — ce module pourrait aussi tourner seul, pointé vers n'importe
# quelle instance SAMCAM via BASE_URL.
BASE_URL = os.environ.get("SAMCAM_INTERNAL_URL", "http://127.0.0.1:8000")

WHATSAPP_VERIFY_TOKEN    = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_ACCESS_TOKEN    = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_API_VERSION     = os.environ.get("WHATSAPP_API_VERSION", "v21.0")

STATE_PATH = os.path.join(ROOT, "data", "whatsapp_state.json")

_ZONES = ["Kribi", "Ebolowa", "Kumba", "Bafoussam", "Yaounde_peri",
          "Ngaoundere", "Garoua", "Maroua",
          "Ndop", "Foumbot", "Kaele", "Guider", "Meiganga",
          "Mbalmayo", "Bafia", "Bertoua", "Nkongsamba", "Buea"]
_ZONE_ALIASES = {
    "kribi": "Kribi", "ebolowa": "Ebolowa", "kumba": "Kumba",
    "bafoussam": "Bafoussam",
    "yaounde": "Yaounde_peri", "yaounde peri": "Yaounde_peri",
    "yaounde-peri": "Yaounde_peri", "yaounde_peri": "Yaounde_peri",
    "ngaoundere": "Ngaoundere", "ngaoundéré": "Ngaoundere",
    "garoua": "Garoua", "maroua": "Maroua",
    "ndop": "Ndop", "foumbot": "Foumbot",
    "kaele": "Kaele", "kaélé": "Kaele",
    "guider": "Guider", "meiganga": "Meiganga",
    "mbalmayo": "Mbalmayo", "bafia": "Bafia",
    "bertoua": "Bertoua", "nkongsamba": "Nkongsamba", "buea": "Buea",
}
_TYPES_EVENEMENT = {"inondation": "inondation", "secheresse": "secheresse",
                     "sécheresse": "secheresse", "chaleur": "chaleur",
                     "canicule": "chaleur"}

router = APIRouter()


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _detecter_zone(texte_norm: str) -> Optional[str]:
    for alias, zone in _ZONE_ALIASES.items():
        if alias in texte_norm:
            return zone
    return None


def _lire_etat() -> dict:
    if not os.path.isfile(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _sauver_etat(etat: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(etat, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[whatsapp_bot] Erreur écriture état : {e}")


_MESSAGE_AIDE = (
    "🌦️ *SAMCAM — Alerte climatique*\n\n"
    "Envoyez le nom d'une zone pour son bulletin de risque :\n"
    "Kribi, Ebolowa, Kumba, Bafoussam, Yaoundé, Ngaoundéré, Garoua, Maroua,\n"
    "Ndop, Foumbot, Kaélé, Guider, Meiganga, Mbalmayo, Bafia, Bertoua, "
    "Nkongsamba, Buea\n\n"
    "Exemples :\n"
    "• \"Maroua\" → bulletin complet\n"
    "• \"risque à Garoua cette semaine ?\" → réponse en langage naturel\n"
    "• \"signalement inondation Maroua eau dans les rues\" → signaler un événement\n\n"
    "Tapez *aide* à tout moment pour revoir ce message."
)


def _formater_bulletin_whatsapp(zone: str, bulletin: dict) -> str:
    def pct(bloc: dict, key: str) -> str:
        return f"{bloc.get('scores', {}).get(f'score_{key}', 0.0) * 100:.0f}%"

    actuel = bulletin.get("risque_actuel", {})
    niveau = actuel.get("niveau_alerte", "INCONNU")
    lignes = [
        f"🌦️ *{zone}* — niveau {niveau}",
        "",
        "Aujourd'hui :",
        f"  💧 Inondation : {pct(actuel, 'inondation')}",
        f"  🌾 Sécheresse : {pct(actuel, 'secheresse')}",
        f"  🔥 Chaleur : {pct(actuel, 'chaleur')}",
        "",
        "Prévisions (niveau global) :",
    ]
    for label, cle in (("3j", "risque_prevu_3j"), ("7j", "risque_prevu_7j"),
                        ("10j", "risque_prevu_10j"), ("14j", "risque_prevu_14j")):
        bloc = bulletin.get(cle, {})
        niv = bloc.get("niveau_alerte")
        if niv and niv != "INCONNU":
            lignes.append(f"  J+{label} : {niv}")
    lignes.append("")
    lignes.append("Écrivez une question pour un conseil détaillé (ex. "
                   f"\"puis-je semer à {zone} cette semaine ?\").")
    return "\n".join(lignes)


async def _appeler_api(method: str, path: str, **kwargs) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.request(method, f"{BASE_URL}{path}", **kwargs)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        print(f"[whatsapp_bot] Erreur appel API {path} : {e}")
        return None


async def _traiter_message(numero: str, texte: str) -> str:
    texte_norm = _sans_accents(texte.strip().lower())
    etat = _lire_etat()

    if texte_norm in ("aide", "help", "bonjour", "salut", "menu", "?"):
        return _MESSAGE_AIDE

    # ── Signalement : "signalement <type> <zone> <description...>" ──────────
    if texte_norm.startswith(("signalement", "signaler")):
        type_evt = next((v for k, v in _TYPES_EVENEMENT.items() if k in texte_norm),
                         "autre")
        zone = _detecter_zone(texte_norm) or etat.get(numero, {}).get("zone")
        if not zone:
            return ("Pour signaler un événement, précisez la zone. Exemple : "
                    "\"signalement inondation Maroua eau dans les rues\"")
        description = re.sub(r"(?i)signalement|signaler", "", texte).strip()
        resultat = await _appeler_api("POST", "/api/signalement", json={
            "zone": zone, "type_evenement": type_evt, "description": description,
        })
        if resultat is None:
            return "Désolé, votre signalement n'a pas pu être enregistré. Réessayez plus tard."
        etat.setdefault(numero, {})["zone"] = zone
        _sauver_etat(etat)
        return f"✅ Signalement enregistré pour {zone} ({type_evt}). Merci pour votre contribution !"

    zone_detectee = _detecter_zone(texte_norm)
    zone = zone_detectee or etat.get(numero, {}).get("zone")

    if zone:
        etat.setdefault(numero, {})["zone"] = zone
        _sauver_etat(etat)

    # ── Zone seule (ou juste détectée pour la première fois) → bulletin complet ──
    mots_hors_zone = texte_norm
    for alias in _ZONE_ALIASES:
        mots_hors_zone = mots_hors_zone.replace(alias, "")
    est_juste_le_nom_de_zone = len(mots_hors_zone.strip()) <= 2

    if not zone:
        return ("Je n'ai pas reconnu de zone SAMCAM dans votre message. "
                "Tapez *aide* pour la liste des zones et des exemples.")

    if zone_detectee and est_juste_le_nom_de_zone:
        bulletin = await _appeler_api("GET", "/api/risk", params={"zone": zone})
        if bulletin is None:
            return f"Désolé, le bulletin de {zone} est momentanément indisponible."
        return _formater_bulletin_whatsapp(zone, bulletin)

    # ── Question libre → assistant IA, grounded sur le bulletin réel ────────
    resultat = await _appeler_api("POST", "/api/assistant",
                                   json={"zone": zone, "question": texte})
    if resultat is None:
        return ("Désolé, l'assistant est momentanément indisponible. "
                f"Tapez juste \"{zone}\" pour le bulletin brut.")
    return resultat.get("reponse", "Désolé, je n'ai pas pu générer de réponse.")


async def _envoyer_message_whatsapp(numero: str, texte: str) -> None:
    if not (WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID):
        print("[whatsapp_bot] Envoi ignoré : WHATSAPP_ACCESS_TOKEN / "
              "WHATSAPP_PHONE_NUMBER_ID non configurés.")
        return
    url = (f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/"
           f"{WHATSAPP_PHONE_NUMBER_ID}/messages")
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texte[:4096]},  # limite WhatsApp par message
    }
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code >= 400:
                print(f"[whatsapp_bot] Erreur envoi WhatsApp ({r.status_code}) : {r.text}")
    except httpx.HTTPError as e:
        print(f"[whatsapp_bot] Erreur réseau envoi WhatsApp : {e}")


@router.get("/webhook/whatsapp", tags=["WhatsApp"])
def verifier_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Poignée de main de vérification exigée par Meta lors de la configuration
    du webhook dans la console WhatsApp Business. Renvoie hub_challenge tel
    quel si le jeton correspond à WHATSAPP_VERIFY_TOKEN.
    """
    if hub_mode == "subscribe" and WHATSAPP_VERIFY_TOKEN and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        return Response(content=hub_challenge or "", media_type="text/plain")
    return Response(content="Forbidden", status_code=403)


@router.post("/webhook/whatsapp", tags=["WhatsApp"])
async def recevoir_message(request: Request):
    """
    Reçoit les messages entrants WhatsApp (format Meta Cloud API), génère
    une réponse via l'API SAMCAM, et la renvoie sur WhatsApp. Répond
    toujours 200 rapidement (Meta réessaie sinon) — les erreurs internes
    sont journalisées, pas propagées au client Meta.
    """
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return {"status": "ignored"}

    try:
        entree  = payload["entry"][0]
        change  = entree["changes"][0]["value"]
        message = change["messages"][0]
    except (KeyError, IndexError):
        # Notifications de statut (accusé de lecture, etc.) — rien à faire
        return {"status": "ignored"}

    numero = message.get("from", "")
    texte  = (message.get("text") or {}).get("body", "")
    if not (numero and texte):
        return {"status": "ignored"}

    reponse = await _traiter_message(numero, texte)
    await _envoyer_message_whatsapp(numero, reponse)
    return {"status": "ok"}
