import { useEffect } from 'react';
import ReportCard from '../components/ReportCard';
import { useCityStore } from '../store/cityStore';

const ReportsView = () => {
  const { reports, loadReports } = useCityStore();

  useEffect(() => {
    loadReports().catch(() => {});
  }, [loadReports]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 rounded-2xl border border-amber-400/25 bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.08),_rgba(109,72,27,0.1))] p-6 shadow-2xl shadow-amber-900/30">
        <h1 className="text-3xl font-semibold text-amber-50">Reportes</h1>
        <p className="text-amber-100/80">Resultados de batallas y misiones de espionaje</p>
      </div>

      <div className="space-y-4">
        {reports.length === 0 && (
          <p className="rounded-xl border border-amber-400/20 bg-black/20 p-4 text-amber-100/70 shadow-inner shadow-black/30">
            No hay reportes aún.
          </p>
        )}
        {reports.map((r) => (
          <ReportCard key={r.id} report={r} />
        ))}
      </div>
    </div>
  );
};

export default ReportsView;
