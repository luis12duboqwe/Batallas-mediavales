import { useEffect, useState } from 'react';
import axiosClient from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';

const QuestsView = () => {
  const [quests, setQuests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [claiming, setClaiming] = useState(null);
  const { currentCity } = useCityStore();

  useEffect(() => {
    fetchQuests();
  }, []);

  const fetchQuests = () => {
    setLoading(true);
    axiosClient.get('/quest/list')
      .then(res => {
        setQuests(res.data.quests || []);
      })
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  };

  const handleClaim = (questId) => {
    setClaiming(questId);
    axiosClient.post(`/quest/claim/${questId}`)
      .then(res => {
        // Update local state
        setQuests(prev => prev.map(q => 
          q.quest_id === questId ? { ...q, is_claimed: true, is_completed: true } : q
        ));
        // Ideally show a toast with the reward
        alert(`Recompensa reclamada: ${res.data.granted_reward}`);
      })
      .catch(err => {
        alert(err.response?.data?.detail || 'Error al reclamar');
      })
      .finally(() => setClaiming(null));
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-amber-100">Misiones</h1>
          <p className="text-amber-200/60">Completa tareas para obtener recompensas</p>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <span className="loading loading-spinner text-amber-500"></span>
        </div>
      ) : (
        <div className="grid gap-4">
          {quests.length === 0 && (
            <div className="text-center py-8 text-gray-400 bg-black/20 rounded-xl">
              No hay misiones disponibles.
            </div>
          )}
          {quests.map(quest => (
            <div key={quest.quest_id} className={`card p-4 border ${quest.is_completed ? 'border-emerald-500/30 bg-emerald-900/10' : 'border-amber-900/30 bg-black/20'}`}>
              <div className="flex items-center justify-between">
                <div>
                  <h3 className={`text-lg font-bold ${quest.is_completed ? 'text-emerald-200' : 'text-amber-100'}`}>
                    {quest.title}
                  </h3>
                  <p className="text-sm text-gray-300 mt-1">{quest.description}</p>
                  <p className="text-xs text-amber-400 mt-2">Recompensa: {quest.reward_description}</p>
                </div>
                <div>
                  {quest.is_claimed ? (
                    <span className="badge badge-success bg-emerald-500/20 text-emerald-200 border-emerald-500/50">Completado</span>
                  ) : quest.is_completed ? (
                    <button 
                      className="btn btn-sm btn-primary bg-emerald-600 hover:bg-emerald-500 border-none text-white quest-claim-btn"
                      onClick={() => handleClaim(quest.quest_id)}
                      disabled={claiming === quest.quest_id}
                    >
                      {claiming === quest.quest_id ? 'Reclamando...' : 'Reclamar'}
                    </button>
                  ) : (
                    <span className="badge badge-ghost text-gray-400">En progreso</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default QuestsView;
