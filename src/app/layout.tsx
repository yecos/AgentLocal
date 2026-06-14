import type { Metadata } from "next";
import { Geist_Mono } from "next/font/google";
import "./globals.css";

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AgentLocal — Agente IA Local",
  description: "Interfaz de agente IA 100% local con Ollama. Sin nube, sin API keys. Procesamiento privado en tu máquina.",
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className="dark" suppressHydrationWarning>
      <body
        className={`${geistMono.variable} mono antialiased bg-[#000000] text-[#e0e0e0]`}
        style={{ fontFamily: "var(--font-geist-mono), 'JetBrains Mono', 'Fira Code', ui-monospace, monospace" }}
      >
        {children}
      </body>
    </html>
  );
}
