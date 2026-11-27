import { Link } from "react-router-dom";
import { usePageTitle } from "../components/usePageTitle";

const TITLE = "Comment ça marche";

/** Texte provisoire : la page sera réécrite dans une tâche suivante. */
export default function HowItWorksPage() {
  const h1 = usePageTitle(TITLE);
  return (
    <article>
      <h1 ref={h1} tabIndex={-1}>{TITLE}</h1>
      <p>
        Chaque citoyen compose sa une : <strong>dix sujets</strong> au plus, modifiables jusqu’à 17 h. À 17 h, Citizen News
        agrège toutes les unes individuelles et publie une une collective, figée jusqu’au lendemain.
      </p>
      <p>
        <Link to="/composer">Composer ma une</Link> · <Link to="/archives">Voir les archives</Link>
      </p>
    </article>
  );
}
