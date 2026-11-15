import type { Metadata } from "next";
import Link from "next/link";
import { SessionBar, SessionProvider } from "./session";
import "./globals.css";

export const metadata: Metadata = {
  title: "Prior-Auth Workbench",
  description: "Prior-authorization requests checked, gathered and queued for people to decide.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SessionProvider>
          <header className="top">
            <Link href="/" className="brand">
              Prior-Auth Workbench
            </Link>
            <SessionBar />
          </header>
          <main>{children}</main>
          <footer>
            Personal learning project. Tallowmere Health Plan and every member, provider and note here are made up.
            People make every decision.
          </footer>
        </SessionProvider>
      </body>
    </html>
  );
}
