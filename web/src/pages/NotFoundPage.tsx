import { Link } from "react-router-dom";
import { Placeholder } from "../components/Placeholder";

export default function NotFoundPage() {
  return (
    <Placeholder title="Page introuvable">
      <p>
        Cette page n’existe pas. <Link to="/">Retour à la une</Link>
      </p>
    </Placeholder>
  );
}
