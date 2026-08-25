import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';

const RESOURCE_OPTIONS = [
  { value: 'wood', label: 'Madera' },
  { value: 'stone', label: 'Piedra' },
  { value: 'iron', label: 'Hierro' },
  { value: 'gold', label: 'Oro' },
];

const EMPTY_TRANSPORT = { target_city_id: '', wood: 0, stone: 0, iron: 0, gold: 0 };

const resourceLabel = (value) => (
  RESOURCE_OPTIONS.find((option) => option.value === value)?.label || value
);

const MarketView = () => {
  const { currentCity, loadCity } = useCityStore();
  const [activeTab, setActiveTab] = useState('send');
  const [offers, setOffers] = useState([]);
  const [commerceRules, setCommerceRules] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageKind, setMessageKind] = useState('status');
  const [filterAlliance, setFilterAlliance] = useState(false);

  const [transport, setTransport] = useState({ ...EMPTY_TRANSPORT });
  const [newOffer, setNewOffer] = useState({
    offer_type: 'wood',
    offer_amount: 100,
    request_type: 'stone',
    request_amount: 100,
    is_alliance_only: false,
  });
  const [npcTrade, setNpcTrade] = useState({ offer_type: 'wood', request_type: 'stone', amount: 100 });

  const showSuccess = (text) => {
    setMessageKind('status');
    setMessage(text);
  };

  const showError = (error, fallback) => {
    setMessageKind('error');
    setMessage(error.response?.data?.detail || fallback);
  };

  useEffect(() => {
    let mounted = true;
    api.getBalance()
      .then((snapshot) => {
        if (mounted) setCommerceRules(snapshot?.market || null);
      })
      .catch((error) => {
        console.warn('Unable to load commerce rules', error);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (currentCity) return undefined;
    let mounted = true;
    loadCity().catch((error) => {
      console.warn('Unable to initialize market city', error);
      if (mounted) {
        setMessageKind('error');
        setMessage('No se pudo cargar la ciudad para abrir el mercado.');
      }
    });
    return () => {
      mounted = false;
    };
  }, [currentCity, loadCity]);

  const fetchOffers = useCallback(async () => {
    if (!currentCity) return;
    try {
      const response = await api.getOffers(currentCity.world_id, filterAlliance);
      setOffers(response.data);
    } catch (error) {
      showError(error, 'No se pudieron cargar las ofertas.');
    }
  }, [currentCity, filterAlliance]);

  useEffect(() => {
    if (activeTab === 'offers' || activeTab === 'my_offers') {
      fetchOffers();
    }
  }, [activeTab, fetchOffers]);

  const refreshAfterMutation = async ({ refreshOffers = false } = {}) => {
    await loadCity();
    if (refreshOffers) await fetchOffers();
  };

  const handleSendResources = async (event) => {
    event.preventDefault();
    if (!currentCity) return;
    setLoading(true);
    setMessage('');
    try {
      await api.sendResources(currentCity.id, currentCity.world_id, transport);
      setTransport({ ...EMPTY_TRANSPORT });
      await refreshAfterMutation();
      showSuccess('Recursos enviados. La capacidad del comerciante se libera cuando regrese.');
    } catch (error) {
      showError(error, 'Error al enviar recursos.');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateOffer = async (event) => {
    event.preventDefault();
    if (!currentCity) return;
    setLoading(true);
    setMessage('');
    try {
      await api.createOffer(currentCity.id, currentCity.world_id, newOffer);
      await refreshAfterMutation({ refreshOffers: true });
      showSuccess('Oferta creada correctamente.');
    } catch (error) {
      showError(error, 'Error al crear oferta.');
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
      await refreshAfterMutation({ refreshOffers: true });
      showSuccess('Oferta aceptada. Ambos envíos viajan mediante comerciantes.');
    } catch (error) {
      showError(error, 'Error al aceptar oferta.');
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
      await refreshAfterMutation({ refreshOffers: true });
      showSuccess('Oferta cancelada.');
    } catch (error) {
      showError(error, 'Error al cancelar oferta.');
    } finally {
      setLoading(false);
    }
  };

  const handleNpcTrade = async (event) => {
    event.preventDefault();
    if (!currentCity) return;
    setLoading(true);
    setMessage('');
    try {
      const response = await api.npcTrade(
        currentCity.id,
        currentCity.world_id,
        npcTrade.offer_type,
        npcTrade.request_type,
        npcTrade.amount,
      );
      await refreshAfterMutation();
      showSuccess(
        `Intercambio NPC: entregaste ${response.data.offered_amount} ${resourceLabel(response.data.offered_resource)} y recibiste ${response.data.received_amount} ${resourceLabel(response.data.received_resource)}.`,
      );
    } catch (error) {
      showError(error, 'Error en intercambio NPC.');
    } finally {
      setLoading(false);
    }
  };

  if (!currentCity) return <div role="status">Cargando ciudad...</div>;

  const otherOffers = offers.filter((offer) => offer.city_id !== currentCity.id);
  const myOffers = offers.filter((offer) => offer.city_id === currentCity.id);
  const npcRate = commerceRules?.npc_trade_rate ?? null;
  const npcReceivedPreview = npcRate === null
    ? '—'
    : Math.floor((Number(npcTrade.amount) || 0) * npcRate);
  const minOfferAmount = commerceRules?.min_offer_amount ?? 1;
  const npcMinAmount = commerceRules?.npc_trade_min_amount ?? 1;
  const npcMaxAmount = commerceRules?.npc_trade_max_amount;
  const tabs = [
    ['send', 'Enviar Recursos'],
    ['offers', 'Mercado'],
    ['my_offers', 'Mis Ofertas'],
    ['npc', 'Comerciante NPC'],
  ];

  return (
    <div className="p-3 sm:p-6 max-w-4xl mx-auto pb-24 md:pb-20">
      <h1 className="text-2xl sm:text-3xl font-bold text-amber-500 mb-4">Mercado</h1>

      {commerceRules && (
        <section
          className="card bg-black/40 border border-amber-900/30 p-4 mb-6 text-sm text-amber-100"
          data-testid="commerce-rules"
          data-rules-version={commerceRules.rules_version}
          aria-label="Reglas comerciales activas"
        >
          <div className="font-semibold">Comercio disponible desde el inicio</div>
          <div className="text-gray-300 mt-1">
            Capacidad base {commerceRules.base_merchant_capacity}; la Plaza Comercial añade {commerceRules.merchant_capacity_per_level} por nivel.
            Los comerciantes permanecen ocupados hasta regresar y un envío que no cabe completo vuelve al remitente sin perder recursos.
          </div>
          <div className="text-gray-400 mt-1">
            Máximo {commerceRules.max_active_offers} ofertas activas · ratio solicitado/ofrecido entre {commerceRules.market_ratio_min} y {commerceRules.market_ratio_max}.
          </div>
        </section>
      )}

      <div className="flex gap-1 overflow-x-auto rounded-lg bg-black/40 p-1 mb-6" role="tablist" aria-label="Secciones del mercado">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={activeTab === id}
            className={`tab shrink-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400 ${activeTab === id ? 'tab-active bg-amber-700' : ''}`}
            onClick={() => setActiveTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {message && (
        <div
          role={messageKind === 'error' ? 'alert' : 'status'}
          aria-live="polite"
          className={`alert mb-4 ${messageKind === 'error' ? 'alert-error' : 'alert-success'}`}
        >
          {message}
        </div>
      )}

      {activeTab === 'send' && (
        <section className="card bg-black/40 border border-amber-900/30 p-4 sm:p-6" aria-labelledby="market-send-heading">
          <h2 id="market-send-heading" className="text-xl font-bold text-amber-100 mb-4">Enviar Recursos</h2>
          <p className="text-sm text-gray-300 mb-4">
            El envío es todo-o-devuelto: si el almacén destino no tiene espacio para el cargamento completo cuando llega, los recursos regresan contigo.
          </p>
          <form onSubmit={handleSendResources} className="space-y-4">
            <div>
              <label htmlFor="market-target-city" className="label">ID Ciudad Destino</label>
              <input
                id="market-target-city"
                type="number"
                min="1"
                inputMode="numeric"
                className="input input-bordered w-full bg-black/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                value={transport.target_city_id}
                onChange={(event) => setTransport({ ...transport, target_city_id: parseInt(event.target.value, 10) || '' })}
                required
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {RESOURCE_OPTIONS.map((resource) => (
                <div key={resource.value}>
                  <label htmlFor={`market-send-${resource.value}`} className="label text-amber-200">{resource.label}</label>
                  <input
                    id={`market-send-${resource.value}`}
                    type="number"
                    min="0"
                    inputMode="numeric"
                    className="input input-bordered w-full bg-black/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                    value={transport[resource.value]}
                    onChange={(event) => setTransport({
                      ...transport,
                      [resource.value]: Math.max(parseInt(event.target.value, 10) || 0, 0),
                    })}
                  />
                </div>
              ))}
            </div>
            <button type="submit" className="btn btn-primary w-full mt-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-200" disabled={loading}>
              {loading ? 'Enviando...' : 'Enviar Comerciantes'}
            </button>
          </form>
        </section>
      )}

      {activeTab === 'offers' && (
        <section className="card bg-black/40 border border-amber-900/30 p-4 sm:p-6" aria-labelledby="market-offers-heading">
          <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mb-4">
            <h2 id="market-offers-heading" className="text-xl font-bold text-amber-100">Ofertas Disponibles</h2>
            <label className="label cursor-pointer justify-start gap-2">
              <input
                type="checkbox"
                className="checkbox checkbox-primary"
                checked={filterAlliance}
                onChange={(event) => setFilterAlliance(event.target.checked)}
              />
              <span className="label-text text-amber-200">Solo Alianza</span>
            </label>
          </div>
          <div className="overflow-x-auto">
            <table className="table w-full">
              <thead>
                <tr>
                  <th>Ofrece</th>
                  <th>Pide</th>
                  <th>Ratio</th>
                  <th>Acceso</th>
                  <th>Acción</th>
                </tr>
              </thead>
              <tbody>
                {otherOffers.map((offer) => (
                  <tr key={offer.id}>
                    <td className="text-green-400">{offer.offer_amount} {resourceLabel(offer.offer_type)}</td>
                    <td className="text-red-400">{offer.request_amount} {resourceLabel(offer.request_type)}</td>
                    <td>{offer.offer_amount > 0 ? (offer.request_amount / offer.offer_amount).toFixed(2) : '—'}</td>
                    <td>{offer.is_alliance_only ? 'Alianza' : 'Pública'}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-sm btn-success focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                        onClick={() => handleAcceptOffer(offer.id)}
                        disabled={loading}
                      >
                        Aceptar
                      </button>
                    </td>
                  </tr>
                ))}
                {otherOffers.length === 0 && (
                  <tr><td colSpan="5" className="text-center text-gray-400">No hay ofertas disponibles</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {activeTab === 'my_offers' && (
        <div className="space-y-6">
          <section className="card bg-black/40 border border-amber-900/30 p-4 sm:p-6" aria-labelledby="market-create-heading">
            <h2 id="market-create-heading" className="text-xl font-bold text-amber-100 mb-2">Crear Oferta</h2>
            {commerceRules && (
              <p className="text-sm text-gray-300 mb-4">
                Mínimo {commerceRules.min_offer_amount} por lado; máximo {commerceRules.max_active_offers} ofertas activas.
              </p>
            )}
            <form onSubmit={handleCreateOffer} className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
              <fieldset>
                <legend className="label">Ofrezco</legend>
                <div className="flex flex-col sm:flex-row gap-2">
                  <label htmlFor="market-offer-amount" className="sr-only">Cantidad ofrecida</label>
                  <input
                    id="market-offer-amount"
                    type="number"
                    min={minOfferAmount}
                    inputMode="numeric"
                    className="input input-bordered w-full bg-black/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                    value={newOffer.offer_amount}
                    onChange={(event) => setNewOffer({ ...newOffer, offer_amount: Math.max(parseInt(event.target.value, 10) || 0, 0) })}
                    required
                  />
                  <label htmlFor="market-offer-resource" className="sr-only">Recurso ofrecido</label>
                  <select
                    id="market-offer-resource"
                    className="select select-bordered bg-black/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                    value={newOffer.offer_type}
                    onChange={(event) => setNewOffer({ ...newOffer, offer_type: event.target.value })}
                  >
                    {RESOURCE_OPTIONS.map((resource) => <option key={resource.value} value={resource.value}>{resource.label}</option>)}
                  </select>
                </div>
              </fieldset>
              <fieldset>
                <legend className="label">Pido</legend>
                <div className="flex flex-col sm:flex-row gap-2">
                  <label htmlFor="market-request-amount" className="sr-only">Cantidad solicitada</label>
                  <input
                    id="market-request-amount"
                    type="number"
                    min={minOfferAmount}
                    inputMode="numeric"
                    className="input input-bordered w-full bg-black/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                    value={newOffer.request_amount}
                    onChange={(event) => setNewOffer({ ...newOffer, request_amount: Math.max(parseInt(event.target.value, 10) || 0, 0) })}
                    required
                  />
                  <label htmlFor="market-request-resource" className="sr-only">Recurso solicitado</label>
                  <select
                    id="market-request-resource"
                    className="select select-bordered bg-black/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                    value={newOffer.request_type}
                    onChange={(event) => setNewOffer({ ...newOffer, request_type: event.target.value })}
                  >
                    {RESOURCE_OPTIONS.map((resource) => <option key={resource.value} value={resource.value}>{resource.label}</option>)}
                  </select>
                </div>
              </fieldset>
              <label className="label cursor-pointer justify-start gap-3 md:col-span-2">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={newOffer.is_alliance_only}
                  onChange={(event) => setNewOffer({ ...newOffer, is_alliance_only: event.target.checked })}
                />
                <span className="label-text text-amber-200">Solo miembros de mi alianza pueden aceptar esta oferta</span>
              </label>
              <button type="submit" className="btn btn-primary w-full md:col-span-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-200" disabled={loading}>
                Crear Oferta
              </button>
            </form>
          </section>

          <section className="card bg-black/40 border border-amber-900/30 p-4 sm:p-6" aria-labelledby="market-mine-heading">
            <h2 id="market-mine-heading" className="text-xl font-bold text-amber-100 mb-4">Mis Ofertas Activas</h2>
            <div className="overflow-x-auto">
              <table className="table w-full">
                <thead>
                  <tr>
                    <th>Ofrezco</th>
                    <th>Pido</th>
                    <th>Acceso</th>
                    <th>Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {myOffers.map((offer) => (
                    <tr key={offer.id}>
                      <td className="text-green-400">{offer.offer_amount} {resourceLabel(offer.offer_type)}</td>
                      <td className="text-red-400">{offer.request_amount} {resourceLabel(offer.request_type)}</td>
                      <td>{offer.is_alliance_only ? 'Alianza' : 'Pública'}</td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-sm btn-error focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                          onClick={() => handleCancelOffer(offer.id)}
                          disabled={loading}
                        >
                          Cancelar
                        </button>
                      </td>
                    </tr>
                  ))}
                  {myOffers.length === 0 && (
                    <tr><td colSpan="4" className="text-center text-gray-400">No tienes ofertas activas</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}

      {activeTab === 'npc' && (
        <section className="card bg-black/40 border border-amber-900/30 p-4 sm:p-6" aria-labelledby="market-npc-heading">
          <h2 id="market-npc-heading" className="text-xl font-bold text-amber-100 mb-2">
            Comerciante NPC {npcRate === null ? '' : `(${Math.round(npcRate * 100)}% de retorno)`}
          </h2>
          <p className="text-gray-300 mb-4 text-sm">
            Conversión instantánea con pérdida controlada para evitar una fuente infinita de intercambio.
            {commerceRules && ` Por operación puedes entregar entre ${commerceRules.npc_trade_min_amount} y ${commerceRules.npc_trade_max_amount}.`}
          </p>
          <form onSubmit={handleNpcTrade} className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
            <fieldset>
              <legend className="label">Dar</legend>
              <div className="flex flex-col sm:flex-row gap-2">
                <label htmlFor="market-npc-amount" className="sr-only">Cantidad para intercambiar</label>
                <input
                  id="market-npc-amount"
                  type="number"
                  min={npcMinAmount}
                  max={npcMaxAmount}
                  inputMode="numeric"
                  className="input input-bordered w-full bg-black/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                  value={npcTrade.amount}
                  onChange={(event) => setNpcTrade({ ...npcTrade, amount: Math.max(parseInt(event.target.value, 10) || 0, 0) })}
                  required
                />
                <label htmlFor="market-npc-offer-resource" className="sr-only">Recurso entregado</label>
                <select
                  id="market-npc-offer-resource"
                  className="select select-bordered bg-black/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                  value={npcTrade.offer_type}
                  onChange={(event) => setNpcTrade({ ...npcTrade, offer_type: event.target.value })}
                >
                  {RESOURCE_OPTIONS.map((resource) => <option key={resource.value} value={resource.value}>{resource.label}</option>)}
                </select>
              </div>
            </fieldset>
            <fieldset>
              <legend className="label">Recibir</legend>
              <div className="flex flex-col sm:flex-row gap-2">
                <label htmlFor="market-npc-receive-amount" className="sr-only">Cantidad recibida</label>
                <input
                  id="market-npc-receive-amount"
                  data-testid="market-npc-received"
                  type="text"
                  className="input input-bordered w-full bg-black/50"
                  value={npcReceivedPreview}
                  disabled
                />
                <label htmlFor="market-npc-request-resource" className="sr-only">Recurso recibido</label>
                <select
                  id="market-npc-request-resource"
                  className="select select-bordered bg-black/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
                  value={npcTrade.request_type}
                  onChange={(event) => setNpcTrade({ ...npcTrade, request_type: event.target.value })}
                >
                  {RESOURCE_OPTIONS.map((resource) => <option key={resource.value} value={resource.value}>{resource.label}</option>)}
                </select>
              </div>
            </fieldset>
            <button type="submit" className="btn btn-warning w-full md:col-span-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-900" disabled={loading}>
              Intercambiar
            </button>
          </form>
        </section>
      )}
    </div>
  );
};

export default MarketView;
