import type { Metadata } from "next";
import { ExportView } from "@/components/export/ExportView";

export const metadata: Metadata = { title: "Exportar" };

export default async function ExportPage({ params }: PageProps<"/temas/[id]/exportar">) {
  const { id } = await params;
  return <ExportView songId={id} />;
}
