import { formatDate } from '../utils/format';

const ReportCard = ({ report }) => (
  <div className="card p-5 flex flex-col gap-3 relative overflow-hidden">
    <div className="absolute inset-0 bg-gradient-to-r from-gray-800/40 via-gray-900/0 to-gray-800/40 pointer-events-none" />
    <div className="flex items-center justify-between relative z-10">
      <div className="flex items-center gap-3">
        <span className="h-10 w-10 rounded-full bg-gray-800/80 border border-yellow-800/40 flex items-center justify-center text-lg">📜</span>
        <div>
          <h3 className="text-lg">{report.title}</h3>
          <p className="text-xs text-gray-400">{formatDate(report.createdAt)}</p>
        </div>
      </div>
      <span className="badge">Resumen</span>
    </div>
    <div
      className="prose prose-invert max-w-none relative z-10 md:columns-2 gap-6 report-body"
      dangerouslySetInnerHTML={{ __html: report.body }}
    />
  </div>
);

export default ReportCard;
