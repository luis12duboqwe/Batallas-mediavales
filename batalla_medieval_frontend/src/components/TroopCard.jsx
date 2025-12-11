import { useState } from 'react';
import { formatNumber } from '../utils/format';
import Timer from './Timer';

const TroopCard = ({ troop, onTrain }) => {
  const [amount, setAmount] = useState(1);

  const handleTrain = () => {
    onTrain({ unit: troop.name, amount: Number(amount) });
  };

  return (
    <div className="card p-5 flex flex-col gap-4 relative overflow-hidden group transition hover:-translate-y-1 hover:shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
      <div className="absolute inset-0 bg-gradient-to-br from-amber-400/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition" />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-11 w-11 rounded-lg bg-gray-800/80 border border-yellow-800/40 flex items-center justify-center text-xl">⚔️</div>
          <div>
            <h3 className="text-lg leading-none">{troop.name}</h3>
            <p className="text-xs text-gray-400">Entrena unidades</p>
          </div>
        </div>
        {troop.trainingEnds && <Timer endTime={troop.trainingEnds} />}
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs text-gray-300">
        <span className="tooltip" data-tip="Poder ofensivo">⚔️ Ataque {troop.attack}</span>
        <span className="tooltip" data-tip="Resistencia defensiva">🛡️ Defensa {troop.defense}</span>
        <span className="tooltip" data-tip="Tiempo que tarda en llegar a destino">🏇 Velocidad {troop.speed}</span>
      </div>
      <div className="text-sm text-gray-400 flex items-center justify-between">
        <span className="tooltip" data-tip="Coste de entrenamiento">🪵 {formatNumber(troop.cost?.wood || 0)} | 🧱 {formatNumber(troop.cost?.clay || 0)} | ⛓️ {formatNumber(troop.cost?.iron || 0)}</span>
        <span className="text-yellow-200 text-xs">Tiempo: {troop.cost?.time ? `${troop.cost.time}s` : 'Instantáneo'}</span>
      </div>
      <div className="flex items-center gap-2">
        <input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} className="input w-24" />
        <button onClick={handleTrain} className="btn-primary">Entrenar</button>
      </div>
      <div className="floating-panel">
        <span className="text-yellow-200">Requisitos</span>
        <span className="text-[11px] text-gray-200">Población disponible + recursos</span>
      </div>
    </div>
  );
};

export default TroopCard;
