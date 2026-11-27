import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useCurrentEdition } from "../api/hooks";
import { usePageTitle } from "../components/usePageTitle";
import { editionPath } from "../components/EditionView";
import { formatEditionDate, formatHour, plural } from "../lib/format";
import styles from "./HowItWorksPage.module.css";

const TITLE = "Comment ça marche";

const SECTIONS = [
  { id: "cycle", title: "Le cycle d’une journée" },
  { id: "regroupement", title: "Comment les articles sont regroupés" },
  { id: "hasard", title: "Comment fonctionne le tirage au hasard" },
  { id: "recents-radar", title: "« Récents » et « Sous les radars »" },
  { id: "agregation", title: "Comment les unes sont agrégées" },
  { id: "compteurs", title: "Pourquoi les compteurs sont cachés pendant la composition" },
  { id: "compte", title: "Pourquoi un compte est nécessaire" },
  { id: "limites", title: "Ce qui n’existe pas encore" },
  { id: "participation", title: "La participation à la dernière édition" },
];

function Section({ id, children }: { id: string; children: ReactNode }) {
  const title = SECTIONS.find((s) => s.id === id)!.title;
  return (
    <section className={styles.section} aria-labelledby={`t-${id}`} id={id}>
      <h2 id={`t-${id}`}>
        {title}
        <a className={styles.anchor} href={`#${id}`} aria-label={`Lien vers la section « ${title} »`}>
          #
        </a>
      </h2>
      {children}
    </section>
  );
}

/** Explication de la méthode (contrat V2) : cycle, regroupement, tirage, agrégation, transparence. */
export default function HowItWorksPage() {
  const h1 = usePageTitle(TITLE);
  const current = useCurrentEdition();
  const edition = current.data?.edition ?? null;
  const nextClose = current.data?.next_close_at;
  const localHour = nextClose ? formatHour(nextClose) : "";

  return (
    <article className={styles.page}>
      <h1 ref={h1} tabIndex={-1}>{TITLE}</h1>
      <p className={styles.lead}>
        Citizen News ne décide pas de ce qui compte. Chaque jour, des citoyens choisissent dix sujets parmi ceux que les médias ont traités, et
        leurs choix, additionnés, forment la une du lendemain. Voici, sans jargon, comment cela se passe.
      </p>

      <nav className={styles.toc} aria-label="Sommaire de la page">
        <h2>Sommaire</h2>
        <ol>
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <a href={`#${s.id}`}>{s.title}</a>
            </li>
          ))}
        </ol>
      </nav>

      <Section id="cycle">
        <ol>
          <li>
            Tout au long de la journée, nous collectons les articles publiés par les médias que nous suivons, puis nous les <strong>regroupons
            par sujet</strong>.
          </li>
          <li>
            Jusqu’à 17 h (heure de Paris), chaque citoyen compose <strong>sa une</strong> : <strong>dix sujets</strong> au plus, tous de même poids,
            sans ordre.
          </li>
          <li>
            À la clôture, nous <strong>agrégeons</strong> toutes les unes et publions <strong>la une citoyenne</strong>. Elle est ensuite{" "}
            <strong>figée jusqu’au lendemain</strong> : elle ne change plus.
          </li>
        </ol>
        <p className={styles.note}>
          <strong>Heure de clôture : 17 h, heure de Paris.</strong>
          {localHour && (
            <>
              {" "}
              Sur votre appareil, la prochaine clôture a lieu à{" "}
              <time dateTime={nextClose}>{localHour}</time> (heure locale).
            </>
          )}
        </p>
        <p>Après la clôture, la composition s’ouvre pour l’édition suivante, avec une une vide.</p>
      </Section>

      <Section id="regroupement">
        <p>
          Nous comparons le texte des articles (leur titre et leur début) : deux articles qui parlent du même événement se ressemblent par les
          mots qu’ils emploient. Les articles très proches sont rangés dans le même sujet. C’est un calcul de <strong>similarité de
          texte</strong>, sans avis éditorial.
        </p>
        <ul>
          <li>
            <strong>Un sujet doit être couvert par au moins 2 médias différents</strong>. Un article que personne d’autre ne reprend n’est pas un
            sujet.
          </li>
          <li>
            <strong>Seuls les sujets encore dans la liste à la clôture comptent</strong> : si un sujet a quitté la liste avant 17 h, les
            approbations qu’il avait reçues ne sont pas retenues.
          </li>
          <li>
            <strong>Les sujets du jour</strong> sont ceux qui comptent au moins un article publié dans les dernières 24 heures. Un sujet plus
            ancien sort de la liste quand plus aucun média n’en parle.
          </li>
        </ul>
      </Section>

      <Section id="hasard">
        <p>
          L’onglet <strong>« Au hasard »</strong> évite de montrer toujours les mêmes sujets en premier.
        </p>
        <ul>
          <li>Chaque personne reçoit <strong>son propre ordre</strong>, tiré d’une graine créée au début de sa visite (une session de navigation).</li>
          <li>
            <strong>Chaque sujet a la même chance</strong> d’arriver en tête : aucune pondération, ni par popularité, ni par média, ni par
            fraîcheur.
          </li>
          <li>
            <strong>Aucune répétition</strong> pendant la session : un sujet déjà passé sous vos yeux vient avant les autres dans votre liste, et
            n’est pas retiré au hasard une seconde fois.
          </li>
          <li>Quand un nouveau sujet apparaît, il s’insère <strong>au hasard</strong> parmi ceux que vous n’avez pas encore vus.</li>
        </ul>
      </Section>

      <Section id="recents-radar">
        <h3>Récents</h3>
        <p>Les sujets classés selon leur date de dernière mise à jour, du plus récent au plus ancien.</p>
        <h3>Sous les radars</h3>
        <p>
          Les sujets couverts par <strong>peu de médias : trois au plus</strong>. Seule compte la faible couverture médiatique : le sujet n’est
          ni jugé moins important ni moins fiable, il est simplement moins repris. Ils sont classés comme dans « Récents ».
        </p>
        <p>Un sujet que vous avez déjà dans votre une reste dans la liste, marqué « Dans ma une ».</p>
      </Section>

      <Section id="agregation">
        <p>
          Le <strong>score</strong> d’un sujet est le nombre de citoyens qui l’ont mis dans leur une. Un citoyen ne compte qu’une fois par
          sujet ; tous les sujets d’une une pèsent autant.
        </p>
        <p>La une publiée retient <strong>les dix premiers sujets</strong>, ayant au moins une approbation. En cas d’égalité de score :</p>
        <ol>
          <li>le sujet couvert par <strong>le plus grand nombre de médias</strong> passe devant ;</li>
          <li>sinon, celui dont la <strong>mise à jour est la plus récente</strong> ;</li>
          <li>sinon, un <strong>ordre fixe</strong> (l’identifiant du sujet) départage, pour que le résultat ne dépende jamais du hasard.</li>
        </ol>
        <p>
          La une publiée indique, pour chaque sujet, le nombre d’approbations et la <strong>proportion</strong> des unes qui le contiennent.
        </p>
      </Section>

      <Section id="compteurs">
        <p>
          Pendant la composition, <strong>aucun compteur n’est visible</strong> : ni le nombre de citoyens qui ont choisi un sujet, ni un
          classement provisoire. Ainsi chacun choisit ce qui lui paraît important, sans suivre la foule (le conformisme). Les compteurs
          apparaissent <strong>avec la une publiée</strong>.
        </p>
      </Section>

      <Section id="compte">
        <ul>
          <li>Il faut <strong>une une par personne et par jour</strong> : le compte garantit qu’on ne compte pas deux fois la même personne.</li>
          <li>La connexion se fait par un <strong>lien magique envoyé par e-mail</strong> : pas de mot de passe à retenir.</li>
          <li>Les actions sont <strong>limitées en débit</strong> pour freiner les abus automatiques.</li>
          <li>Vous pouvez parcourir les sujets sans compte ; le brouillon de votre une est retrouvé à la connexion.</li>
        </ul>
        <p>Les e-mails ne sont jamais publiés ; la une collective n’affiche que des totaux.</p>
      </Section>

      <Section id="limites">
        <p>Citizen News est jeune. Soyons francs sur ce qui manque :</p>
        <ul>
          <li>
            <strong>Pas de détection avancée de manipulation</strong> : nous limitons les abus (un compte, une une par jour, limitation de débit),
            mais nous ne repérons pas encore les campagnes coordonnées.
          </li>
          <li><strong>Pas de thèmes</strong> (politique, sport, culture…) pour le moment.</li>
          <li><strong>Pas de recherche</strong> pour le moment.</li>
        </ul>
      </Section>

      <Section id="participation">
        {current.isPending && <p role="status">Chargement…</p>}
        {edition ? (
          <p>
            La dernière une, celle du <Link to={editionPath(edition.date)}>{formatEditionDate(edition.date)}</Link>, a réuni{" "}
            <strong>{plural(edition.participants, "participant", "participants")}</strong>.{" "}
            <Link to="/archives">Voir l’archive des éditions</Link>.
          </p>
        ) : (
          !current.isPending && (
            <p>
              Aucune une n’a encore été publiée. Les participants de chaque édition seront comptés ici dès la première. Les unes passées
              seront rangées dans <Link to="/archives">l’archive</Link>.
            </p>
          )
        )}
      </Section>

      <p className={styles.cta}>
        <Link to="/composer">Composer ma une</Link>
        <Link to="/archives">Voir les archives</Link>
      </p>
    </article>
  );
}
