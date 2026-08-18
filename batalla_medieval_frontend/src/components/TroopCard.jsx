import { useState } from 'react';
import { formatNumber } from '../utils/format';
import Timer from './Timer';

const TroopCard = ({ troop, onTrain }) => {
  const [amount, setAmount] = useState(1);
  const [submitting, setSubmitting] = useState(false);

  const researched = Boolean(troop.researched);
  const requirementsMet = Boolean(troop.training_requirements_met);
  const canSubmit = researched && requirementsMet && Number(amount) > 0 && !submitting;

  const handleTrain = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      await onTrain({ troopType: troop.unit_type, amount: Number(amount) });
    } finally {
      setSubmitting(false);
    }
  };

  const requirementText = Object.entries(troop.training_requirements || {})
    .map(([name, level]) => `${name} Nv. ${level}`)
    .join(', ');

  return (
    <div className="card p-5 flex flex-col gap-4 relative overflow-hidden group transition hover:-translate-y-1 hover:shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
      <div className="absolute inset-0 bg-gradient-to-br from-amber-400/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition" />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-11 w-11 rounded-lg bg-gray-800/80 border border-yellow-800/40 flex items-center justify-center text-xl">⚔️</div>
          <div>
            <h3 className="text-lg leading-none">{troop.unit_type}</h3>
            <p className="text-xs text-gray-400">Entrena unidades</p>
          </div>
        </div>
        {troop.trainingEnds && <Timer endTime={troop.trainingEnds} />}
      </div>

      <div className="text-sm text-gray-400 flex items-center justify-between gap-3 flex-wrap">
        <span className="tooltip" data-tip="Coste por unidad">
          🪵 {formatNumber(troop.training_cost?.wood || 0)} | 🧱 {formatNumber(troop.training_cost?.clay || 0)} | ⛓️ {formatNumber(troop.training_cost?.iron || 0)}
        </span>
        <span className="text-yellow-200 text-xs">
          Tiempo/unidad: {troop.training_time_seconds}s
        </span>
      </div>

      {!researched && (
        <div className="text-red-400 text-sm font-bold text-center border border-red-400/30 rounded p-2 bg-red-400/10">
          🔒 Requiere investigación
        </div>
      )}
      {researched && !requirementsMet && (
        <div className="text-amber-300 text-xs border border-amber-500/30 rounded p-2 bg-amber-500/10">
          Requisitos: {requirementText || 'No disponibles'}
        </div>
      )}

      <div className="flex items-center gap-2">
        <input
          type="number"
          min="1"
          step="1"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          disabled={!researched || !requirementsMet || submitting}
          className="input w-24"
        />
        <button
          onClick={handleTrain}
          disabled={!canSubmit}
          className={`btn-primary recruit-btn-${troop.unit_type} disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {submitting ? 'Enviando…' : 'Entrenar'}
        </button>
      </div>

      <div className="floating-panel">
        <span className="text-yellow-200">Servidor autoritativo</span>
        <span className="text-[11px] text-gray-200">
          {requirementText || 'Sin requisitos de edificio'}
        </span>
      </div>
    </div>
  );
};

export default TroopCard;
