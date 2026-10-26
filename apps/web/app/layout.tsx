import type { Metadata, Viewport } from "next";
import { Courier_Prime, Schibsted_Grotesk } from "next/font/google";
import { TopBar } from "@/components/shell/TopBar";
import { AGENCY_NAME, PRODUCT_NAME } from "@/lib/brand";
import "./globals.css";

const schibsted = Schibsted_Grotesk({
  variable: "--font-schibsted",
  subsets: ["latin", "latin-ext"],
  display: "swap",
});

const courier = Courier_Prime({
  variable: "--font-courier",
  subsets: ["latin", "latin-ext"],
  weight: ["400", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: `${PRODUCT_NAME} · ${AGENCY_NAME}`, template: `%s · ${PRODUCT_NAME}` },
  description:
    "Separá una canción en pistas, revisá su tempo, tonalidad y secciones, y exportá un paquete listo para el show.",
};

export const viewport: Viewport = {
  themeColor: "#141210",
  colorScheme: "dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es" className={`${schibsted.variable} ${courier.variable}`}>
      <body>
        <TopBar />
        {children}
      </body>
    </html>
  );
}
