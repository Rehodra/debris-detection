import History from "./pages/History";
import { useState } from "react";
import Nav from "./components/Nav";
import Footer from "./components/Footer";
import Home from "./pages/Home";
import Dashboard from "./pages/Dashboard";
import MapPage from "./pages/Map";
import Reports from "./pages/Reports";
import SonarAnalysis from "./pages/SonarAnalysis";
import HowItWorks from "./pages/Howitworks";
import Sidebar from "./components/Sidebar";

export type Page = "home" | "dashboard" | "map" | "reports" | "how-it-works" | "sonar-analysis" | "history";

export default function App() {
  const [page, setPage] = useState<Page>("home");

  const navigate = (p: Page) => {
    setPage(p);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className={`app-shell ${page === "home" ? "app-shell--landing" : "app-shell--workspace"}`}>
      {(page === "home" || page === "dashboard") && <Nav currentPage={page} onNavigate={navigate} />}

      {page !== "home" && page !== "dashboard" && <Sidebar currentPage={page} onNavigate={navigate} />}
      <main className="app-content">
        {page === "home" && <Home onNavigate={navigate} />}
        {page === "dashboard" && <Dashboard />}
        {page === "sonar-analysis" && <SonarAnalysis />}
        {page === "map" && <MapPage />}
        {page === "reports" && <Reports />}
        {page === "how-it-works" && <HowItWorks onNavigate={navigate} />}
        {page === "history" && <History />}
      </main>

      {page !== "map" && page !== "dashboard" && page !== "sonar-analysis" && (
        <Footer onNavigate={navigate} />
      )}
    </div>
  );
}
