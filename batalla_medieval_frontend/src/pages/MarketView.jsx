import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';
import { useUserStore } from '../store/userStore';

const MarketView = () => {
  const { t } = useTranslation();
  const { currentCity, fetchCityStatus } = useCityStore();
  const { user } = useUserStore();
  const [activeTab, setActiveTab] = useState('send'); // send, offers, my_offers, npc
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [filterAlliance, setFilterAlliance] = useState(false);

  // Send Resources Form
  const [transport, setTransport] = useState({ target_city_id: '', wood: 0, clay: 0, iron: 0 });

  // Create Offer Form
  const [newOffer, setNewOffer] = useState({ offer_type: 'wood', offer_amount: 1000, request_type: 'clay', request_amount: 1000 });

  // NPC Trade Form
  const [npcTrade, setNpcTrade] = useState({ offer_type: 'wood', request_type: 'clay', amount: 1000 });

  useEffect(() => {
    if (activeTab === 'offers' || activeTab === 'my_offers') {
      fetchOffers();
    }
  }, [activeTab, currentCity, filterAlliance]);

  const fetchOffers = async () => {
    if (!currentCity) return;
    setLoading(true);
    try {
      const res = await api.getOffers(currentCity.world_id, filterAlliance);
      setOffers(res.data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleSendResources = async (e) => {
    e.preventDefault();
    if (!currentCity) return;
    setLoading(true);
    setMessage('');
    try {
      await api.sendResources(currentCity.id, currentCity.world_id, transport);
      setMessage('Recursos enviados correctamente');
      setTransport({ target_city_id: '', wood: 0, clay: 0, iron: 0 });
      fetchCityStatus(currentCity.id, currentCity.world_id);
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Error al enviar recursos');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateOffer = async (e) => {
    e.preventDefault();
    if (!currentCity) return;
    setLoading(true);
    setMessage('');
    try {
      await api.createOffer(currentCity.id, currentCity.world_id, newOffer);
      setMessage('Oferta creada correctamente');
      fetchOffers();
      fetchCityStatus(currentCity.id, currentCity.world_id);
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Error al crear oferta');
    } finally {
      setLoading(false);
    }
  };

  const handleAcceptOffer = async (offerId) => {
    if (!currentCity) return;
    setLoading(true);
    setMessage('');
    try {
      await api.acceptOffer(offerId, currentCity.id, currentCity.world_id);
      setMessage('Oferta aceptada');
      fetchOffers();
      fetchCityStatus(currentCity.id, currentCity.world_id);
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Error al aceptar oferta');
    } finally {
      setLoading(false);
    }
  };

  const handleCancelOffer = async (offerId) => {
    if (!currentCity) return;
    setLoading(true);
    setMessage('');
    try {
      await api.cancelOffer(offerId, currentCity.id, currentCity.world_id);
      setMessage('Oferta cancelada');
      fetchOffers();
      fetchCityStatus(currentCity.id, currentCity.world_id);
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Error al cancelar oferta');
    } finally {
      setLoading(false);
    }
  };

  const handleNpcTrade = async (e) => {
    e.preventDefault();
    if (!currentCity) return;
    setLoading(true);
    setMessage('');
    try {
      await api.npcTrade(currentCity.id, currentCity.world_id, npcTrade.offer_type, npcTrade.request_type, npcTrade.amount);
      setMessage('Intercambio NPC realizado (1:1)');
      fetchCityStatus(currentCity.id, currentCity.world_id);
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Error en intercambio NPC');
    } finally {
      setLoading(false);
    }
  };

  if (!currentCity) return <div>Cargando ciudad...</div>;

  return (
    <div className="p-6 max-w-4xl mx-auto pb-20">
      <h1 className="text-3xl font-bold text-amber-500 mb-6">Mercado</h1>

      <div className="tabs tabs-boxed bg-black/40 mb-6">
        <a className={`tab ${activeTab === 'send' ? 'tab-active bg-amber-700' : ''}`} onClick={() => setActiveTab('send')}>Enviar Recursos</a>
        <a className={`tab ${activeTab === 'offers' ? 'tab-active bg-amber-700' : ''}`} onClick={() => setActiveTab('offers')}>Mercado</a>
        <a className={`tab ${activeTab === 'my_offers' ? 'tab-active bg-amber-700' : ''}`} onClick={() => setActiveTab('my_offers')}>Mis Ofertas</a>
        <a className={`tab ${activeTab === 'npc' ? 'tab-active bg-amber-700' : ''}`} onClick={() => setActiveTab('npc')}>Comerciante NPC</a>
      </div>

      {message && (
        <div className={`alert mb-4 ${message.includes('Error') ? 'alert-error' : 'alert-success'}`}>
          {message}
        </div>
      )}

      {activeTab === 'send' && (
        <div className="card bg-black/40 border border-amber-900/30 p-6">
          <h2 className="text-xl font-bold text-amber-100 mb-4">Enviar Recursos</h2>
          <form onSubmit={handleSendResources} className="space-y-4">
            <div>
              <label className="label">ID Ciudad Destino</label>
              <input
                type="number"
                className="input input-bordered w-full bg-black/50"
                value={transport.target_city_id}
                onChange={(e) => setTransport({ ...transport, target_city_id: parseInt(e.target.value) || '' })}
                required
              />
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="label text-amber-200">Madera</label>
                <input
                  type="number"
                  className="input input-bordered w-full bg-black/50"
                  value={transport.wood}
                  onChange={(e) => setTransport({ ...transport, wood: parseInt(e.target.value) || 0 })}
                />
              </div>
              <div>
                <label className="label text-amber-200">Barro</label>
                <input
                  type="number"
                  className="input input-bordered w-full bg-black/50"
                  value={transport.clay}
                  onChange={(e) => setTransport({ ...transport, clay: parseInt(e.target.value) || 0 })}
                />
              </div>
              <div>
                <label className="label text-amber-200">Hierro</label>
                <input
                  type="number"
                  className="input input-bordered w-full bg-black/50"
                  value={transport.iron}
                  onChange={(e) => setTransport({ ...transport, iron: parseInt(e.target.value) || 0 })}
                />
              </div>
            </div>
            <button type="submit" className="btn btn-primary w-full mt-4" disabled={loading}>
              {loading ? 'Enviando...' : 'Enviar Comerciantes'}
            </button>
          </form>
        </div>
      )}

      {activeTab === 'offers' && (
        <div className="space-y-4">
          <div className="card bg-black/40 border border-amber-900/30 p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold text-amber-100">Ofertas Disponibles</h2>
              <label className="label cursor-pointer gap-2">
                <span className="label-text text-amber-200">Solo Alianza</span>
                <input 
                  type="checkbox" 
                  className="checkbox checkbox-primary"
                  checked={filterAlliance}
                  onChange={(e) => setFilterAlliance(e.target.checked)}
                />
              </label>
            </div>
            <div className="overflow-x-auto">
              <table className="table w-full">
                <thead>
                  <tr>
                    <th>Ofrece</th>
                    <th>Pide</th>
                    <th>Ratio</th>
                    <th>Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {offers.filter(o => o.city_id !== currentCity.id).map(offer => (
                    <tr key={offer.id}>
                      <td className="text-green-400">{offer.offer_amount} {offer.offer_type}</td>
                      <td className="text-red-400">{offer.request_amount} {offer.request_type}</td>
                      <td>{(offer.offer_amount / offer.request_amount).toFixed(2)}</td>
                      <td>
                        <button 
                          className="btn btn-sm btn-success"
                          onClick={() => handleAcceptOffer(offer.id)}
                          disabled={loading}
                        >
                          Aceptar
                        </button>
                      </td>
                    </tr>
                  ))}
                  {offers.filter(o => o.city_id !== currentCity.id).length === 0 && (
                    <tr><td colSpan="4" className="text-center text-gray-500">No hay ofertas disponibles</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'my_offers' && (
        <div className="space-y-6">
          <div className="card bg-black/40 border border-amber-900/30 p-6">
            <h2 className="text-xl font-bold text-amber-100 mb-4">Crear Oferta</h2>
            <form onSubmit={handleCreateOffer} className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
              <div>
                <label className="label">Ofrezco</label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    className="input input-bordered w-full bg-black/50"
                    value={newOffer.offer_amount}
                    onChange={(e) => setNewOffer({ ...newOffer, offer_amount: parseInt(e.target.value) || 0 })}
                  />
                  <select
                    className="select select-bordered bg-black/50"
                    value={newOffer.offer_type}
                    onChange={(e) => setNewOffer({ ...newOffer, offer_type: e.target.value })}
                  >
                    <option value="wood">Madera</option>
                    <option value="clay">Barro</option>
                    <option value="iron">Hierro</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="label">Pido</label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    className="input input-bordered w-full bg-black/50"
                    value={newOffer.request_amount}
                    onChange={(e) => setNewOffer({ ...newOffer, request_amount: parseInt(e.target.value) || 0 })}
                  />
                  <select
                    className="select select-bordered bg-black/50"
                    value={newOffer.request_type}
                    onChange={(e) => setNewOffer({ ...newOffer, request_type: e.target.value })}
                  >
                    <option value="wood">Madera</option>
                    <option value="clay">Barro</option>
                    <option value="iron">Hierro</option>
                  </select>
                </div>
              </div>
              <button type="submit" className="btn btn-primary w-full md:col-span-2" disabled={loading}>
                Crear Oferta
              </button>
            </form>
          </div>

          <div className="card bg-black/40 border border-amber-900/30 p-6">
            <h2 className="text-xl font-bold text-amber-100 mb-4">Mis Ofertas Activas</h2>
            <div className="overflow-x-auto">
              <table className="table w-full">
                <thead>
                  <tr>
                    <th>Ofrezco</th>
                    <th>Pido</th>
                    <th>Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {offers.filter(o => o.city_id === currentCity.id).map(offer => (
                    <tr key={offer.id}>
                      <td className="text-green-400">{offer.offer_amount} {offer.offer_type}</td>
                      <td className="text-red-400">{offer.request_amount} {offer.request_type}</td>
                      <td>
                        <button 
                          className="btn btn-sm btn-error"
                          onClick={() => handleCancelOffer(offer.id)}
                          disabled={loading}
                        >
                          Cancelar
                        </button>
                      </td>
                    </tr>
                  ))}
                  {offers.filter(o => o.city_id === currentCity.id).length === 0 && (
                    <tr><td colSpan="3" className="text-center text-gray-500">No tienes ofertas activas</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'npc' && (
        <div className="card bg-black/40 border border-amber-900/30 p-6">
          <h2 className="text-xl font-bold text-amber-100 mb-4">Comerciante NPC (Ratio 1:1)</h2>
          <p className="text-gray-400 mb-4 text-sm">Intercambia recursos instantáneamente con el comerciante del juego.</p>
          <form onSubmit={handleNpcTrade} className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
            <div>
              <label className="label">Dar</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  className="input input-bordered w-full bg-black/50"
                  value={npcTrade.amount}
                  onChange={(e) => setNpcTrade({ ...npcTrade, amount: parseInt(e.target.value) || 0 })}
                />
                <select
                  className="select select-bordered bg-black/50"
                  value={npcTrade.offer_type}
                  onChange={(e) => setNpcTrade({ ...npcTrade, offer_type: e.target.value })}
                >
                  <option value="wood">Madera</option>
                  <option value="clay">Barro</option>
                  <option value="iron">Hierro</option>
                </select>
              </div>
            </div>
            <div>
              <label className="label">Recibir</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  className="input input-bordered w-full bg-black/50"
                  value={npcTrade.amount}
                  disabled
                />
                <select
                  className="select select-bordered bg-black/50"
                  value={npcTrade.request_type}
                  onChange={(e) => setNpcTrade({ ...npcTrade, request_type: e.target.value })}
                >
                  <option value="wood">Madera</option>
                  <option value="clay">Barro</option>
                  <option value="iron">Hierro</option>
                </select>
              </div>
            </div>
            <button type="submit" className="btn btn-warning w-full md:col-span-2" disabled={loading}>
              Intercambiar (Coste: 0 Oro)
            </button>
          </form>
        </div>
      )}
    </div>
  );
};

export default MarketView;
