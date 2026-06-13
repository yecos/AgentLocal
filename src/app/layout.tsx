import type { Metadata } from "next";
import { Geist_Mono } from "next/font/google";
import "./globals.css";

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ZAI — Agent Interface",
  description: "Futuristic minimal-tech chat interface for local AI agents running on Ollama",
  icons: {
    icon: "https://z-cdn.chatglm.cn/z-ai/static/logo.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${geistMono.variable} mono antialiased bg-[#000000] text-[#e0e0e0]`}
        style={{ fontFamily: "var(--font-geist-mono), 'JetBrains Mono', 'Fira Code', ui-monospace, monospace" }}
      >
        {children}
      </body>
    </html>
  );
}
