import { Link } from "react-router-dom";
import { Placeholder } from "../components/Placeholder";

/** Page provisoire : la composition de la une arrive avec la tâche suivante. */
export default function ComposerPage() {
  return (
    <Placeholder title="Composer ma une">
      <p>
        La composition de votre une arrive très bientôt. En attendant, <Link to="/">consultez la une du jour</Link>.
      </p>
    </Placeholder>
  );
}
