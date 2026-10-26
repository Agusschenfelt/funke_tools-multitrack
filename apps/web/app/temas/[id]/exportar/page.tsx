import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Exportar" };

/** Placeholder until the export screen lands (T5). */
export default async function ExportPage({ params }: PageProps<"/temas/[id]/exportar">) {
  const { id } = await params;
  return (
    <main style={{ maxWidth: "64rem", margin: "0 auto", padding: "2rem 1rem 4.5rem" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 800, textTransform: "uppercase" }}>Exportar</h1>
      <p style={{ marginTop: "0.75rem", color: "var(--paper-dim)" }}>
        La exportación todavía no está disponible.
      </p>
      <Link
        href={`/temas/${id}/estudio`}
        style={{ display: "inline-flex", alignItems: "center", minHeight: "var(--touch)" }}
      >
        Volver al estudio
      </Link>
    </main>
  );
}
