import type { Metadata } from "next";
import { ThemeProvider } from "next-themes";
import "./globals.css";

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
    <html lang="es" suppressHydrationWarning>
      <body
        className="mono antialiased bg-[#000000] text-[#e0e0e0] dark:bg-[#000000] dark:text-[#e0e0e0]"
        style={{ fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SF Mono', 'Consolas', ui-monospace, monospace" }}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
