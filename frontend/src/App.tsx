/**
 * Authetec console — application routes.
 */
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import Dashboard from "./pages/Dashboard";
import Documents from "./pages/Documents";
import Signatures from "./pages/Signatures";
import Payments from "./pages/Payments";
import Risk from "./pages/Risk";
import Alerts from "./pages/Alerts";
import Evidence from "./pages/Evidence";
import Audit from "./pages/Audit";
import Developers from "./pages/Developers";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/signatures" element={<Signatures />} />
          <Route path="/payments" element={<Payments />} />
          <Route path="/risk" element={<Risk />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/evidence" element={<Evidence />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/developers" element={<Developers />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
