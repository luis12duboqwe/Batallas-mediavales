import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { formatNumber } from '../utils/format';
import Timer from './Timer';

const resourceCostMeta = [
  ['wood', '🪵'],
  ['stone', '🪨'],
  ['iron', '⛓️'],
  ['gold', '🪙'],
];

const TroopCard = ({ troop, onTrain }) => {
  const { t } = useTranslation();
  const [amount, setAmount] = useState(1);
  const [submitting, setSubmitting] = useState(false);

  const researched = Boolean(troop.researched);
  const requirementsMet = Boolean(troop.training_requirements_met);
  const numericAmount = Number(amount);
  const populationCost = Math.max(Number(troop.population_cost || 1), 1);
  const populationAvailable = Math.max(Number(troop.population_available || 0), 0);
  const upkeepPerHour = Math.max(Number(troop.upkeep_per_hour || 0), 0);
  const upkeepAvailable = Math.max(Number(troop.upkeep_available_per_hour || 0), 0);
  const amountFitsPopulation = numericAmount > 0
    && numericAmount * populationCost <= populationAvailable;
  const amountFitsUpkeep = upkeepPerHour === 0
    || numericAmount * upkeepPerHour <= upkeepAvailable + 1e-9;
  const canSubmit = researched
    && requirementsMet
    && numericAmount > 0
    && amountFitsPopulation
    && amountFitsUpkeep
    && !submitting;
  const displayName = t(troop.unit_type);
  const inputId = `train-${troop.unit_type}-amount`;
  const visibleCosts = resourceCostMeta.filter(
    ([resource]) => (troop.training_cost?.[resource] ?? 0) > 0
  );

  const handleTrain = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      await onTrain({ troopType: troop.unit_type, amount: numericAmount });
    } finally {
      setSubmitting(false);
    }
  };

  const requirementText = Object.entries(troop.training_requirements || {})
    .map(([name, level]) => `${t(name)} Nv. ${level}`)
    .join(', ');

  return (
    <article
      className="card p-5 flex flex-col gap-4 relative overflow-hidden group transition hover:-translate-y-1 hover:shadow-[0_18px_45px_rgba(0,0,0,0.45)]"
      data-testid={`troop-card-${troop.unit_type}`}
    >
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-amber-400/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition" />
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="h-11 w-11 shrink-0 rounded-lg bg-gray-800/80 border border-yellow-800/40 flex items-center justify-center text-xl" aria-hidden>⚔️</div>
          <div className="min-w-0">
            <h3 className="text-lg leading-none break-words">{displayName}</h3>
            <p className="text-xs text-gray-400">Entrena unidades</p>
          </div>
        </div>
        {troop.trainingEnds && <Timer endTime={troop.trainingEnds} />}
      </div>

      <div className="text-sm text-gray-300 flex items-center justify-between gap-3 flex-wrap">
        <span className="flex gap-2 flex-wrap">
          {visibleCosts.map(([resource, icon], index) => (
            <span key={resource}>
              {index > 0 && <span className="mr-2">·</span>}
              {icon} {formatNumber(troop.training_cost?.[resource] ?? 0)}
            </span>
          ))}
        </span>
        <span className="text-yellow-200 text-xs">
          Tiempo/unidad: {troop.training_time_seconds}s
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs text-gray-300" data-testid={`troop-stats-${troop.unit_type}`}>
        <span>⚔️ Ataque: {troop.attack}</span>
        <span>🛡️ Def. inf.: {troop.defense_infantry}</span>
        <span>🐎 Def. cab.: {troop.defense_cavalry}</span>
        <span>🏗️ Def. asedio: {troop.defense_siege}</span>
        <span>💨 Velocidad: {troop.movement_speed}</span>
        <span>🎒 Carga: {troop.carry_capacity}</span>
        <span>👥 Población: {populationCost}</span>
        <span>🪙 Mant.: {upkeepPerHour.toFixed(2)}/h</span>
      </div>

      <div className="text-xs text-gray-300" data-testid="military-capacity">
        Población disponible: {populationAvailable} · Oro sostenible libre: {upkeepAvailable.toFixed(2)}/h
      </div>

      {!researched && (
        <div className="text-red-300 text-sm font-bold text-center border border-red-400/30 rounded p-2 bg-red-400/10">
          🔒 Requiere investigación
        </div>
      )}
      {researched && !requirementsMet && (
        <div className="text-amber-300 text-xs border border-amber-500/30 rounded p-2 bg-amber-500/10">
          Requisitos: {requirementText || 'No disponibles'}
        </div>
      )}
      {researched && requirementsMet && !amountFitsPopulation && (
        <div className="text-amber-300 text-xs border border-amber-500/30 rounded p-2 bg-amber-500/10">
          No hay población suficiente para esa cantidad.
        </div>
      )}
      {researched && requirementsMet && amountFitsPopulation && !amountFitsUpkeep && (
        <div
          className="text-amber-300 text-xs border border-amber-500/30 rounded p-2 bg-amber-500/10"
          data-testid={`upkeep-block-${troop.unit_type}`}
        >
          El ingreso estable de oro no alcanza para mantener esa cantidad.
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-end gap-2">
        <div className="flex-1">
          <label htmlFor={inputId} className="block text-xs text-gray-300 mb-1">Cantidad de {displayName}</label>
          <input
            id={inputId}
            type="number"
            min="1"
            step="1"
            inputMode="numeric"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            disabled={!researched || !requirementsMet || submitting}
            className="input w-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
          />
        </div>
        <button
          type="button"
          onClick={handleTrain}
          disabled={!canSubmit}
          className={`btn-primary recruit-btn-${troop.unit_type} sm:min-w-28 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-200 disabled:opacity-50 disabled:cursor-not-allowed`}
          data-testid={`train-action-${troop.unit_type}`}
        >
          {submitting ? 'Enviando…' : 'Entrenar'}
        </button>
      </div>

      <div className="floating-panel pointer-events-none" aria-hidden="true">
        <span className="text-yellow-200">Servidor autoritativo</span>
        <span className="text-[11px] text-gray-200">
          {requirementText || 'Sin requisitos de edificio'}
        </span>
      </div>
    </article>
  );
};

export default TroopCard;
