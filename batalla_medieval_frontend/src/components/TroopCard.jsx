import { useState } from 'react';
import { formatNumber } from '../utils/format';
import Timer from './Timer';

const TroopCard = ({ troop, onTrain }) => {
  const [amount, setAmount] = useState(1);

  const handleTrain = () => {
    onTrain({ unit: troop.name, amount: Number(amount) });
  };

  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-lg">{troop.name}</h3>
        {troop.trainingEnds && <Timer endTime={troop.trainingEnds} />}
      </div>
      <p className="text-sm text-gray-300">Ataque {troop.attack} | Defensa {troop.defense} | Velocidad {troop.speed}</p>
      <p className="text-sm text-gray-400">Coste: 🪵 {formatNumber(troop.cost?.wood || 0)} | 🧱 {formatNumber(troop.cost?.clay || 0)} | ⛓️ {formatNumber(troop.cost?.iron || 0)}</p>
      <div className="flex items-center gap-2">
        <input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} className="input w-24" />
        <button onClick={handleTrain} className="btn-primary">Entrenar</button>
      </div>
    </div>
  );
};

export default TroopCard;
