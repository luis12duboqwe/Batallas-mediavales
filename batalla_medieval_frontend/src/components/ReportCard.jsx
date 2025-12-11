import { formatDate } from '../utils/format';

const ReportCard = ({ report }) => (
  <div className="card p-4 flex flex-col gap-2">
    <div className="flex items-center justify-between">
      <h3 className="text-lg">{report.title}</h3>
      <span className="text-xs text-gray-400">{formatDate(report.createdAt)}</span>
    </div>
    <div className="prose prose-invert max-w-none" dangerouslySetInnerHTML={{ __html: report.body }} />
  </div>
);

export default ReportCard;
