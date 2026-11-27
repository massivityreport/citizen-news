import { usePageTitle } from "../../components/usePageTitle";

export function AdminHomePage() {
  const h1 = usePageTitle("Administration");
  return (
    <section>
      <h1 ref={h1} tabIndex={-1}>
        Administration
      </h1>
      <p>Bienvenue dans le backoffice de Citizen News.</p>
    </section>
  );
}

function Soon({ title }: { title: string }) {
  const h1 = usePageTitle(title);
  return (
    <section>
      <h1 ref={h1} tabIndex={-1}>
        {title}
      </h1>
      <p>Bientôt disponible.</p>
    </section>
  );
}

export const AdminSourcesPage = () => <Soon title="Sources" />;
export const AdminArticlesPage = () => <Soon title="Articles" />;
export const AdminTopicsPage = () => <Soon title="Sujets" />;
