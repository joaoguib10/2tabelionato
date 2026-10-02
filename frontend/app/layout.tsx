import type { Metadata } from "next";
import "./globals.css";

import { AuthProvider } from "../context/AuthContext";

export const metadata: Metadata = {
  title: "Tabeleão",
  description: "Assistente inteligente do tabelionato",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
