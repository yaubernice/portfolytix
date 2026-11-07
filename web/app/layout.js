import { Source_Sans_3 } from "next/font/google";
import AppProviders from "../components/AppProviders";
import ExplainLayer from "../components/ExplainLayer";
import "./globals.css";

const sourceSans = Source_Sans_3({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body-face",
  display: "swap",
});

export const metadata = {
  title: {
    default: "Portfolytix",
    template: "%s · Portfolytix",
  },
  description: "Clarity for what you already own — portfolio intelligence from stored transactions and prices.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "Portfolytix",
    statusBarStyle: "default",
  },
};

export const viewport = {
  themeColor: "#0f1c2e",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={sourceSans.variable} suppressHydrationWarning>
      <body>
        <AppProviders>
          <ExplainLayer />
          <div className="shell">{children}</div>
        </AppProviders>
      </body>
    </html>
  );
}
