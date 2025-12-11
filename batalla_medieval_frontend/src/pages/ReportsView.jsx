import { useEffect } from 'react';
import ReportCard from '../components/ReportCard';
import { useCityStore } from '../store/cityStore';

const ReportsView = () => {
  const { reports, loadReports } = useCityStore();

  useEffect(() => {
    loadReports().catch(() => {});
  }, [loadReports]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Reportes</h1>
          <p className="text-gray-400">Resultados de batallas y espionaje</p>
        </div>
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        {reports.length === 0 && <div className="skeleton h-32 w-full col-span-2" />}
        {reports.length === 0 && <p className="text-gray-400 col-span-2">No hay reportes aún.</p>}
        {reports.map((r) => (
          <ReportCard key={r.id} report={r} />
        ))}
      </div>
    </div>
  );
};

export default ReportsView;
