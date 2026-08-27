import { useEffect, useState } from 'react';
import axiosClient from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';

const RankingView = () => {
  const [activeTab, setActiveTab] = useState('players');
  const [rankings, setRankings] = useState([]);
  const [medals, setMedals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { currentCity } = useCityStore();
  const worldId = currentCity?.world_id;

  useEffect(() => {
    if (!worldId) return;
    setLoading(true);
    setError('');

    if (activeTab === 'medals') {
      axiosClient.get('/achievement/list', { params: { world_id: worldId } })
        .then((res) => setMedals(res.data))
        .catch((err) => setError(err.response?.data?.detail || 'No se pudieron cargar las medallas.'))
        .finally(() => setLoading(false));
      return;
    }

    const endpoint = activeTab === 'players' ? '/ranking/players' : '/ranking/alliances';
    axiosClient.get(endpoint, { params: { world_id: worldId } })
      .then((res) => setRankings(res.data))
      .catch((err) => setError(err.response?.data?.detail || 'No se pudo cargar la clasificación.'))
      .finally(() => setLoading(false));
  }, [activeTab, worldId]);

  const claimMedal = async (achievementId) => {
    if (!worldId) return;
    setError('');
    try {
      await axiosClient.post(`/achievement/claim/${achievementId}`, null, { params: { world_id: worldId } });
      const refreshed = await axiosClient.get('/achievement/list', { params: { world_id: worldId } });
      setMedals(refreshed.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo registrar la medalla.');
    }
  };

  return (
    <div className="space-y-6" data-testid="ranking-view">
      <div>
        <h1 className="text-3xl font-bold text-amber-100">Clasificación y Honor</h1>
        <p className="text-amber-200/60">Posiciones del mundo y medallas de reconocimiento sin ventajas jugables.</p>
      </div>

      <div className="tabs tabs-boxed bg-black/40 p-1" role="tablist" aria-label="Clasificación y medallas">
        {[
          ['players', 'Jugadores'],
          ['alliances', 'Alianzas'],
          ['medals', 'Medallas de honor'],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={activeTab === key}
            data-testid={`ranking-tab-${key}`}
            className={`tab ${activeTab === key ? 'tab-active bg-amber-700 text-white' : 'text-gray-400'}`}
            onClick={() => setActiveTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <div role="alert" className="rounded border border-red-800 bg-red-950/40 p-3 text-red-200">{error}</div>}

      {loading ? (
        <div className="flex justify-center py-12" role="status" aria-label="Cargando">
          <span className="loading loading-spinner text-amber-500" />
        </div>
      ) : activeTab === 'medals' ? (
        <div className="grid gap-4 md:grid-cols-2" data-testid="honor-medals-list">
          {medals.length === 0 && <p className="text-gray-500">No hay medallas configuradas para este mundo.</p>}
          {medals.map(({ achievement, progress }) => {
            const complete = progress.status === 'completed';
            const claimed = progress.status === 'claimed';
            return (
              <article key={achievement.id} className="rounded-xl border border-amber-900/30 bg-black/25 p-4" data-testid={`honor-medal-${achievement.id}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="font-bold text-amber-100">🏅 {achievement.title}</h2>
                    <p className="mt-1 text-sm text-gray-400">{achievement.description}</p>
                  </div>
                  <span className="rounded bg-amber-900/30 px-2 py-1 text-xs text-amber-200">Honor</span>
                </div>
                <div className="mt-4 text-sm text-gray-300">
                  Progreso: {progress.current_progress} / {achievement.requirement_value}
                </div>
                <progress className="progress progress-warning mt-2 w-full" value={Math.min(progress.current_progress, achievement.requirement_value)} max={achievement.requirement_value} />
                <div className="mt-4">
                  {claimed ? (
                    <span className="text-green-300" data-testid={`honor-medal-claimed-${achievement.id}`}>Medalla registrada</span>
                  ) : complete ? (
                    <button
                      type="button"
                      className="btn btn-sm bg-amber-600 text-black border-none"
                      onClick={() => claimMedal(achievement.id)}
                      data-testid={`honor-medal-claim-${achievement.id}`}
                    >
                      Registrar medalla
                    </button>
                  ) : (
                    <span className="text-gray-500">En progreso</span>
                  )}
                </div>
                <p className="mt-3 text-xs text-gray-500">Esta medalla no otorga recursos, tropas ni bonos.</p>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="overflow-x-auto bg-black/20 rounded-xl border border-amber-900/30">
          <table className="table w-full" data-testid={`ranking-table-${activeTab}`}>
            <thead>
              <tr className="text-amber-200/70 border-b border-amber-900/30">
                <th className="bg-transparent">Rango</th>
                <th className="bg-transparent">Nombre</th>
                <th className="bg-transparent text-right">Puntos</th>
              </tr>
            </thead>
            <tbody>
              {rankings.length === 0 && (
                <tr><td colSpan="3" className="text-center py-8 text-gray-500">No hay datos disponibles.</td></tr>
              )}
              {rankings.map((entry) => (
                <tr
                  key={activeTab === 'players' ? entry.user_id : entry.alliance_id}
                  className="hover:bg-white/5 border-b border-amber-900/10"
                  data-testid={`ranking-row-${entry.rank}`}
                >
                  <td className="font-bold text-amber-500">#{entry.rank}</td>
                  <td className="font-medium text-amber-100">{activeTab === 'players' ? entry.username : entry.name}</td>
                  <td className="text-right font-mono text-amber-200">{entry.points?.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default RankingView;
