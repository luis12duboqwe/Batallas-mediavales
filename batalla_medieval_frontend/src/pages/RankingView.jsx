import { useEffect, useState } from 'react';
import axiosClient from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';

const RankingView = () => {
  const [activeTab, setActiveTab] = useState('players');
  const [rankings, setRankings] = useState([]);
  const [loading, setLoading] = useState(false);
  const { currentCity } = useCityStore();

  useEffect(() => {
    if (currentCity?.world_id) {
      fetchRanking();
    }
  }, [activeTab, currentCity]);

  const fetchRanking = () => {
    setLoading(true);
    const endpoint = activeTab === 'players' ? '/ranking/players' : '/ranking/alliances';
    axiosClient.get(endpoint, { params: { world_id: currentCity.world_id } })
      .then(res => {
        setRankings(res.data);
      })
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-amber-100">Clasificación</h1>
          <p className="text-amber-200/60">Los señores más poderosos del reino</p>
        </div>
      </div>

      <div className="tabs tabs-boxed bg-black/40 p-1">
        <a 
          className={`tab ${activeTab === 'players' ? 'tab-active bg-amber-700 text-white' : 'text-gray-400'}`}
          onClick={() => setActiveTab('players')}
        >
          Jugadores
        </a>
        <a 
          className={`tab ${activeTab === 'alliances' ? 'tab-active bg-amber-700 text-white' : 'text-gray-400'}`}
          onClick={() => setActiveTab('alliances')}
        >
          Alianzas
        </a>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <span className="loading loading-spinner text-amber-500"></span>
        </div>
      ) : (
        <div className="overflow-x-auto bg-black/20 rounded-xl border border-amber-900/30">
          <table className="table w-full">
            <thead>
              <tr className="text-amber-200/70 border-b border-amber-900/30">
                <th className="bg-transparent">Rango</th>
                <th className="bg-transparent">Nombre</th>
                <th className="bg-transparent text-right">Puntos</th>
                {activeTab === 'players' && (
                  <>
                    <th className="bg-transparent text-right">Ataque</th>
                    <th className="bg-transparent text-right">Defensa</th>
                  </>
                )}
                {activeTab === 'alliances' && <th className="bg-transparent text-right">Miembros</th>}
              </tr>
            </thead>
            <tbody>
              {rankings.length === 0 && (
                <tr>
                  <td colSpan="6" className="text-center py-8 text-gray-500">
                    No hay datos disponibles.
                  </td>
                </tr>
              )}
              {rankings.map((rank, index) => (
                <tr key={index} className="hover:bg-white/5 border-b border-amber-900/10">
                  <td className="font-bold text-amber-500">#{index + 1}</td>
                  <td className="font-medium text-amber-100">
                    {activeTab === 'players' ? rank.username : rank.name}
                  </td>
                  <td className="text-right font-mono text-amber-200">
                    {rank.points?.toLocaleString()}
                  </td>
                  {activeTab === 'players' && (
                    <>
                      <td className="text-right font-mono text-red-400">
                        {rank.attacker_points?.toLocaleString()}
                      </td>
                      <td className="text-right font-mono text-blue-400">
                        {rank.defender_points?.toLocaleString()}
                      </td>
                    </>
                  )}
                  {activeTab === 'alliances' && (
                    <td className="text-right text-gray-400">{rank.members_count}</td>
                  )}
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
