import { useEffect, useMemo, useState } from 'react';
import ReportCard from '../components/ReportCard';
import { useCityStore } from '../store/cityStore';

const OUTCOME_LABELS = {
  attacker_victory: 'Victoria atacante',
  defender_victory: 'Victoria defensora',
  mutual_destruction: 'Destrucción mutua',
  stalemate: 'Empate',
};

const sumLosses = (losses = {}) => Object.values(losses).reduce((total, value) => total + Number(value || 0), 0);

const parseBattleAudit = (report) => {
  if (report.report_type !== 'battle') return null;
  try {
    const payload = JSON.parse(report.content);
    return payload?.combat?.seed ? payload : null;
  } catch {
    return null;
  }
};

const CombatAuditPanel = ({ payload }) => {
  const combat = payload.combat;
  const rounds = Array.isArray(combat.rounds) ? combat.rounds : [];

  return (
    <div
      className="rounded-2xl border border-cyan-400/20 bg-cyan-950/10 p-4 text-sm shadow-lg shadow-black/20"
      data-testid="combat-audit"
      data-combat-seed={combat.seed}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">Auditoría de combate</p>
          <p className="mt-1 font-semibold text-cyan-50">
            {OUTCOME_LABELS[combat.outcome] || combat.outcome || 'Resultado pendiente'} · {combat.round_count ?? rounds.length} rondas
          </p>
        </div>
        <div className="text-right text-xs text-cyan-100/70">
          <p>{combat.algorithm_version}</p>
          <p>{combat.balance_version}</p>
        </div>
      </div>

      <div className="mt-3 rounded-xl border border-white/10 bg-black/25 p-3">
        <p className="text-xs uppercase tracking-wide text-gray-400">Semilla reproducible</p>
        <code className="mt-1 block break-all font-mono text-xs text-cyan-100" data-testid="combat-seed">
          {combat.seed}
        </code>
      </div>

      {rounds.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[620px] text-left text-xs">
            <thead className="text-cyan-100/70">
              <tr className="border-b border-white/10">
                <th className="px-2 py-2 font-medium">Ronda</th>
                <th className="px-2 py-2 font-medium">Moral</th>
                <th className="px-2 py-2 font-medium">Suerte</th>
                <th className="px-2 py-2 font-medium">Bajas atacante</th>
                <th className="px-2 py-2 font-medium">Bajas defensor</th>
                <th className="px-2 py-2 font-medium">Ataque efectivo</th>
                <th className="px-2 py-2 font-medium">Defensa</th>
              </tr>
            </thead>
            <tbody>
              {rounds.map((round) => (
                <tr key={round.round} className="border-b border-white/5 text-gray-300" data-testid="combat-round">
                  <td className="px-2 py-2 font-semibold text-cyan-100">{round.round}</td>
                  <td className="px-2 py-2">{(Number(round.moral || 0) * 100).toFixed(1)}%</td>
                  <td className="px-2 py-2">{(Number(round.luck || 0) * 100).toFixed(1)}%</td>
                  <td className="px-2 py-2">{sumLosses(round.attacker_losses)}</td>
                  <td className="px-2 py-2">{sumLosses(round.defender_losses)}</td>
                  <td className="px-2 py-2">{Number(round.effective_attack || 0).toFixed(1)}</td>
                  <td className="px-2 py-2">{Number(round.defense_value || 0).toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

const ReportEntry = ({ report }) => {
  const auditPayload = useMemo(() => parseBattleAudit(report), [report]);

  return (
    <div className="space-y-3">
      <ReportCard report={report} />
      {auditPayload && <CombatAuditPanel payload={auditPayload} />}
    </div>
  );
};

const ReportsView = () => {
  const loadReports = useCityStore((state) => state.loadReports);
  const worldId = useCityStore((state) => state.currentCity?.world_id);
  const [reports, setReports] = useState([]);
  const [loadState, setLoadState] = useState('loading');
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let active = true;
    setReports([]);
    setLoadState('loading');
    loadReports().then((result) => {
      if (active) {
        if (!Array.isArray(result?.reports)) throw new Error('La respuesta de reportes es inválida.');
        setReports(result.reports);
        setLoadState('ready');
      }
    }).catch((error) => {
      if (active) {
        console.error('Failed to load reports', error);
        setLoadState('error');
      }
    });
    return () => { active = false; };
  }, [loadReports, worldId, retryKey]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 rounded-2xl border border-amber-400/25 bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.08),_rgba(109,72,27,0.1))] p-6 shadow-2xl shadow-amber-900/30">
        <h1 className="text-3xl font-semibold text-amber-50">Reportes</h1>
        <p className="text-amber-100/80">Resultados de batallas y misiones de espionaje</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {loadState === 'loading' && <div role="status" data-testid="reports-loading" className="skeleton col-span-2 h-32 w-full" aria-label="Cargando reportes" />}
        {loadState === 'error' && (
          <div role="alert" data-testid="reports-load-error" className="col-span-2 rounded border border-red-700 bg-red-950/60 p-4 text-red-100">
            <p>No se pudieron cargar los reportes.</p>
            <button type="button" className="btn-primary mt-3" onClick={() => setRetryKey((value) => value + 1)}>Reintentar reportes</button>
          </div>
        )}
        {loadState === 'ready' && reports.length === 0 && <p data-testid="reports-empty" role="status" className="col-span-2 text-gray-400">No hay reportes aún.</p>}
        {loadState === 'ready' && reports.map((report) => (
          <ReportEntry key={report.id} report={report} />
        ))}
      </div>
    </div>
  );
};

export default ReportsView;
