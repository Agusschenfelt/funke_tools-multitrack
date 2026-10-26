import type { Metadata } from "next";
import { SongPlaceholder } from "@/components/song/SongPlaceholder";

export const metadata: Metadata = { title: "Tema" };

export default async function SongPage({ params }: PageProps<"/temas/[id]">) {
  const { id } = await params;
  return <SongPlaceholder songId={id} />;
}
