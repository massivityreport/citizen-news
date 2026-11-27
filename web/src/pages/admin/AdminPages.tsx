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
