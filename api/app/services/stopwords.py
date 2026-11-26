"""French stop-words, stored accent-folded and lowercase (the vectorizer folds text first)."""

from app.services.text import fold

_WORDS = """
a au aux avec ce ces cet cette ceci cela celle celles celui ceux chez comme comment dans de des du donc dont
elle elles en entre est et etaient etait etant ete etre eu eux il ils je jusqu la le les leur leurs lors lui
ma mais me meme mes moi mon ne ni nos notre nous on ou par pas pour qu que quel quelle quelles quels qui sa
sans se ses si son sur ta te tes toi ton tu un une vos votre vous y
ai as avons avez ont avait avaient aura auront avoir eut fait faire font fut sont sera seront suis es sommes
etes ete serait seraient peut peuvent plus moins tres tout tous toute toutes autre autres aussi apres avant
contre depuis encore deja bien alors ainsi ici voici voila selon sous vers pendant durant afin
cette ca c d j l m n s t qu lundi mardi mercredi jeudi vendredi samedi dimanche
"""

FRENCH_STOP_WORDS: frozenset[str] = frozenset(fold(w) for w in _WORDS.split())
