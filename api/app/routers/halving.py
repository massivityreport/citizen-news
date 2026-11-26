from fastapi import APIRouter

from config.halving import load_halving_params

router = APIRouter()

# One short French sentence per parameter, for the "Comment ça marche" page. Keep in sync with HalvingParams.
DESCRIPTIONS = {
    "min_votes_first_decision": (
        "Chaque nouveau sujet reçoit au moins ce nombre de votes avant la première décision : "
        "aucun sujet n'est écarté sur un échantillon trop mince."
    ),
    "keep_ratio": (
        "À la fin de chaque vague, cette proportion des sujets les mieux notés continue l'aventure ; "
        "les autres passent en réserve."
    ),
    "waves": (
        "Nombre de sélections successives qu'un sujet doit franchir pour devenir émergent ; "
        "le nombre de votes demandé double à chaque vague."
    ),
    "new_topic_traffic_share": (
        "Part des sujets proposés au vote qui sont des nouveautés, pour que chaque sujet ait sa chance."
    ),
    "rescue_share": (
        "Part des sujets proposés au vote tirés parmi ceux mis en réserve, pour les réévaluer : "
        "aucun sujet n'est condamné définitivement."
    ),
}


@router.get("/halving/config")
def halving_config() -> dict:
    """Active Successive Halving parameters and what they mean (public transparency page)."""
    params = load_halving_params()
    return {"params": params.model_dump(), "description": DESCRIPTIONS}
