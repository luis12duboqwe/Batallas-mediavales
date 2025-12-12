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
      <div className="grid gap-4 md:grid-cols-2">
        {reports.length === 0 && <div className="skeleton col-span-2 h-32 w-full" />}
        {reports.length === 0 && <p className="col-span-2 text-gray-400">No hay reportes aún.</p>}
        {reports.map((r) => (
          <ReportCard key={r.id} report={r} />
        ))}
      </div>
    </div>
  );
};

export default ReportsView;
