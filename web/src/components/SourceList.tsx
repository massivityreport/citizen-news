import type { Source } from "../api/types";
import { formatDate, safeHref } from "../lib/format";
import styles from "./Topic.module.css";

export function SourceList({ sources, headingLevel = "h3" }: { sources: Source[]; headingLevel?: "h3" | "h4" }) {
  const Heading = headingLevel;
  if (sources.length === 0) return null;
  return (
    <div className={styles.sources}>
      <Heading className={styles.sourcesTitle}>{sources.length > 1 ? "Sources" : "Source"}</Heading>
      <ul>
        {sources.map((s, i) => {
          const href = safeHref(s.url);
          const date = formatDate(s.published_at);
          return (
            <li key={`${i}-${s.url}`}>
              {href ? (
                <a href={href} target="_blank" rel="noopener noreferrer" title={s.title || undefined}>
                  {s.name}
                  <span className={styles.srOnly}> (nouvel onglet){s.title ? ` : ${s.title}` : ""}</span>
                </a>
              ) : (
                <span>{s.name}</span>
              )}
              {date && <span className={styles.sourceDate}> · {date}</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
