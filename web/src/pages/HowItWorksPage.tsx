import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { HalvingConfig, HalvingParams } from "../api/types";
import { usePageTitle } from "../components/usePageTitle";
import styles from "./HowItWorksPage.module.css";

const TITLE = "Comment ça marche";

type ParamKey = keyof HalvingParams;

const PARAMS: { key: ParamKey; label: string; percent?: boolean }[] = [
  { key: "min_votes_first_decision", label: "Votes avant la première décision" },
  { key: "keep_ratio", label: "Part des sujets conservés à chaque vague", percent: true },
  { key: "waves", label: "Nombre de vagues" },
  { key: "new_topic_traffic_share", label: "Part de l’attention donnée aux nouveaux sujets", percent: true },
  { key: "rescue_share", label: "Part de l’attention donnée au repêchage", percent: true },
];

const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
const formatParam = (value: number, percent?: boolean) => (percent ? `${nf.format(value * 100)}\u00a0%` : nf.format(value));

const REASONS = [
  ["Priorité commune", "une large part des citoyens estime qu’il faut en parler davantage."],
  ["Forte mobilisation", "beaucoup de personnes ont voté sur ce sujet, avec un fort soutien."],
  ["Sous les radars", "peu de votes pour l’instant, mais un soutien marqué chez ceux qui l’ont vu : il mérite d’être montré."],
  ["Sujet émergent", "un sujet récent, encore peu évalué, qui commence à attirer l’attention."],
];

const STEPS = [
  ["Première vague aléatoire", "chaque nouveau sujet est présenté à un échantillon aléatoire de citoyens, de façon garantie : aucun sujet n’est écarté avant d’avoir été vu."],
  ["Sélection", "une fois assez de votes réunis, les sujets les plus soutenus sont conservés pour la vague suivante."],
  ["Accélération", "les sujets conservés sont montrés à davantage de monde pour confirmer ou corriger leur score."],
  ["Réserve", "les sujets moins soutenus ne disparaissent pas : ils passent en réserve et reçoivent moins d’attention."],
  ["Repêchage périodique", "de temps en temps, des sujets de la réserve sont de nouveau proposés. Aucun sujet n’est écarté sur un seul vote : un sujet en réserve peut revenir tant qu’il reste d’actualité."],
];

function Params({ config }: { config: HalvingConfig }) {
  return (
    <dl className={styles.params}>
      {PARAMS.filter((p) => p.key in config.params).map((p) => (
        <div key={p.key} className={styles.param}>
          <dt>{p.label}</dt>
          <dd className={styles.value}>{formatParam(config.params[p.key], p.percent)}</dd>
          {config.description[p.key] && <dd className={styles.desc}>{config.description[p.key]}</dd>}
        </div>
      ))}
    </dl>
  );
}

export default function HowItWorksPage() {
  const h1 = usePageTitle(TITLE);
  const config = useQuery({ queryKey: ["halving-config"], queryFn: api.halvingConfig, staleTime: 10 * 60_000 });

  return (
    <article className={styles.page}>
      <h1 ref={h1} tabIndex={-1}>
        {TITLE}
      </h1>

      <section aria-labelledby="question">
        <h2 id="question">La question posée</h2>
        <p>
          Citizen News ne demande pas « quel article aimez-vous ? » mais <strong>« De quoi devrions-nous parler ? »</strong>.
          Vous jugez l’importance d’un sujet, pas la qualité d’un article.
        </p>
      </section>

      <section aria-labelledby="principe">
        <h2 id="principe">Le principe</h2>
        <ul>
          <li>Les articles de presse sont regroupés par <strong>sujet</strong>.</li>
          <li>Vous avez <strong>un vote par personne et par sujet</strong>, que vous pouvez modifier.</li>
          <li>Les <strong>résultats sont masqués avant votre vote</strong>, pour ne pas vous influencer.</li>
        </ul>
        <p>
          <Link to="/jouer">À vous de jouer</Link>
        </p>
      </section>

      <section aria-labelledby="halving">
        <h2 id="halving">Quels sujets vous sont proposés ?</h2>
        <p>
          Pour que chaque sujet ait sa chance, nous utilisons une méthode de sélection par vagues, le <em>Successive Halving</em> :
        </p>
        <ol className={styles.steps}>
          {STEPS.map(([name, text]) => (
            <li key={name}>
              <strong>{name}</strong> : {text}
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="params" aria-busy={config.isPending}>
        <h2 id="params">Les réglages actuels</h2>
        {config.isPending && <p role="status">Chargement des réglages…</p>}
        {config.isError && (
          <div role="alert">
            <p>Les réglages actuels n’ont pas pu être chargés.</p>
            <button type="button" className={styles.btn} onClick={() => void config.refetch()}>
              Réessayer
            </button>
          </div>
        )}
        {config.data && <Params config={config.data} />}
      </section>

      <section aria-labelledby="raisons">
        <h2 id="raisons">Pourquoi un sujet est-il à la une ?</h2>
        <p>Chaque sujet de la une affiche la raison de sa présence :</p>
        <dl className={styles.reasons}>
          {REASONS.map(([name, text]) => (
            <div key={name}>
              <dt>{name}</dt>
              <dd>{text}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="confidentialite">
        <h2 id="confidentialite">Vos données</h2>
        <p>
          Nous ne conservons que <strong>votre adresse e-mail</strong> et <strong>vos votes</strong>. L’adresse saisie pour
          recevoir un lien n’est gardée que le temps de validité du lien si le compte n’existe pas encore. Vous pouvez voter sans compte :
          vos choix restent alors dans votre navigateur jusqu’à votre <Link to="/connexion">connexion</Link>, par lien envoyé par
          e-mail, sans mot de passe.
        </p>
      </section>
    </article>
  );
}
