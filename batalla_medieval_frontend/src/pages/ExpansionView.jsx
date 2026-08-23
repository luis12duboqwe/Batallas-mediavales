import { useCallback, useEffect, useMemo, useState } from 'react';
import expansionApi from '../api/expansionApi';
import { useCityStore } from '../store/cityStore';
import { formatNumber } from '../utils/format';

const RESOURCE_META = [
  ['wood', '🪵', 'Madera'],
  ['stone', '🪨', 'Piedra'],
  ['iron', '⛓️', 'Hierro'],
  ['gold', '🪙', 'Oro'],
];

const CostLine = ({ cost = {} }) => (
  <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-300">
    {RESOURCE_META.filter(([resource]) => Number(cost[resource] || 0) > 0).map(([resource, icon, label]) => (
      <span key={resource} title={label}>{icon} {formatNumber(cost[resource])}</span>
    ))}
  </div>
);

const ExpansionView = () => {
  const { currentCity, cities, loadCity } = useCityStore();
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({
    name: '',
    x: '',
    y: '',
    settlement_type: 'camp',
  });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [messageKind, setMessageKind] = useState('status');

  const worldId = currentCity?.world_id || cities[0]?.world_id || null;
  const originCity = useMemo(
    () => (currentCity?.settlement_type !== 'camp' ? currentCity : null)
      || cities.find((settlement) => settlement.settlement_type !== 'camp')
      || null,
    [currentCity, cities],
  );
  const camps = useMemo(
    () => cities.filter((settlement) => settlement.settlement_type === 'camp'),
    [cities],
  );

  const loadExpansion = useCallback(async () => {
    const cityData = await loadCity();
    const resolvedWorldId = cityData?.city?.world_id || cityData?.cities?.[0]?.world_id;
    if (!resolvedWorldId) {
      setStatus(null);
      return;
    }
    const response = await expansionApi.getStatus(resolvedWorldId);
    setStatus(response.data);
  }, [loadCity]);

  useEffect(() => {
    loadExpansion().catch((error) => {
      setMessageKind('error');
      setMessage(error.response?.data?.detail || 'No se pudo cargar la expansión.');
    });
  }, [loadExpansion]);

  const handleFound = async (event) => {
    event.preventDefault();
    if (!originCity || !worldId) {
      setMessageKind('error');
      setMessage('Necesitas una ciudad completa como origen de la expansión.');
      return;
    }

    setBusy(true);
    setMessage('');
    try {
      const response = await expansionApi.found({
        origin_city_id: originCity.id,
        name: form.name.trim(),
        x: Number(form.x),
        y: Number(form.y),
        settlement_type: form.settlement_type,
      });
      setMessageKind('status');
      setMessage(
        response.data.settlement_type === 'camp'
          ? 'Campamento fundado correctamente.'
          : 'Ciudad fundada correctamente.',
      );
      setForm((previous) => ({ ...previous, name: '', x: '', y: '' }));
      await loadExpansion();
    } catch (error) {
      setMessageKind('error');
      setMessage(error.response?.data?.detail || 'No se pudo fundar el asentamiento.');
    } finally {
      setBusy(false);
    }
  };

  const handlePromote = async (campId) => {
    setBusy(true);
    setMessage('');
    try {
      await expansionApi.promoteCamp(campId);
      setMessageKind('status');
      setMessage('Campamento promovido a ciudad.');
      await loadExpansion();
    } catch (error) {
      setMessageKind('error');
      setMessage(error.response?.data?.detail || 'No se pudo promover el campamento.');
    } finally {
      setBusy(false);
    }
  };

  const selectedType = form.settlement_type;
  const selectedPointCost = status?.point_costs?.[selectedType] ?? 0;
  const selectedResourceCost = selectedType === 'camp'
    ? status?.camp_founding_cost
    : status?.city_founding_cost;

  return (
    <div className="space-y-6" data-testid="expansion-view">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.25em] text-yellow-600">G6 · Expansión territorial</p>
          <h1 className="text-3xl text-yellow-100">Ciudades y campamentos</h1>
          <p className="mt-2 max-w-3xl text-sm text-gray-400">
            Completa niveles de Iglesia y Catedral para conseguir puntos. Cada expansión consume puntos y recursos del servidor de forma atómica.
          </p>
        </div>
        <div className="card min-w-56 p-4 text-center" data-testid="expansion-points">
          <div className="text-xs uppercase tracking-wider text-gray-400">Puntos de expansión</div>
          <div className="mt-1 text-4xl font-bold text-yellow-300">{status?.expansion_points ?? '—'}</div>
          <div className="mt-1 text-xs text-gray-500">Iglesia +1 · Catedral +3 por nivel completado</div>
        </div>
      </header>

      {message && (
        <div
          role={messageKind === 'error' ? 'alert' : 'status'}
          className={`rounded border p-3 text-sm ${messageKind === 'error' ? 'border-red-700 bg-red-950/50 text-red-200' : 'border-green-700 bg-green-950/40 text-green-200'}`}
        >
          {message}
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-3" aria-label="Resumen territorial">
        <div className="card p-4">
          <div className="text-sm text-gray-400">Ciudades completas</div>
          <div className="mt-1 text-3xl text-amber-200">{status?.city_count ?? 0}</div>
          <p className="mt-2 text-xs text-gray-500">Producción y capacidad completas. Pueden crear nuevos asentamientos.</p>
        </div>
        <div className="card p-4">
          <div className="text-sm text-gray-400">Campamentos</div>
          <div className="mt-1 text-3xl text-amber-200">{status?.camp_count ?? 0}</div>
          <p className="mt-2 text-xs text-gray-500">25% de producción, 50 de población y edificios logísticos limitados.</p>
        </div>
        <div className="card p-4">
          <div className="text-sm text-gray-400">Origen de expansión</div>
          <div className="mt-1 text-lg text-amber-200">{originCity?.name || 'Sin ciudad disponible'}</div>
          <p className="mt-2 text-xs text-gray-500">Los campamentos no pueden fundar otros asentamientos.</p>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <form onSubmit={handleFound} className="card space-y-5 p-5" data-testid="found-settlement-form">
          <div>
            <h2 className="text-xl text-yellow-100">Fundar asentamiento</h2>
            <p className="text-sm text-gray-400">Elige una casilla libre y no acuática dentro del mundo.</p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm text-gray-300">
              Tipo
              <select
                className="input mt-1 w-full"
                value={form.settlement_type}
                onChange={(event) => setForm({ ...form, settlement_type: event.target.value })}
                data-testid="settlement-type"
              >
                <option value="camp">Campamento</option>
                <option value="city">Ciudad</option>
              </select>
            </label>
            <label className="text-sm text-gray-300">
              Nombre
              <input
                required
                maxLength={100}
                className="input mt-1 w-full"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder={selectedType === 'camp' ? 'Campamento del Norte' : 'Nueva Ciudad'}
                data-testid="settlement-name"
              />
            </label>
            <label className="text-sm text-gray-300">
              Coordenada X
              <input
                required
                type="number"
                className="input mt-1 w-full"
                value={form.x}
                onChange={(event) => setForm({ ...form, x: event.target.value })}
                data-testid="settlement-x"
              />
            </label>
            <label className="text-sm text-gray-300">
              Coordenada Y
              <input
                required
                type="number"
                className="input mt-1 w-full"
                value={form.y}
                onChange={(event) => setForm({ ...form, y: event.target.value })}
                data-testid="settlement-y"
              />
            </label>
          </div>

          <div className="rounded border border-yellow-900/50 bg-black/20 p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-gray-300">Coste de expansión</span>
              <span className="font-bold text-yellow-300">✦ {selectedPointCost} puntos</span>
            </div>
            <div className="mt-2"><CostLine cost={selectedResourceCost} /></div>
          </div>

          <button
            type="submit"
            className="btn-primary w-full"
            disabled={busy || !originCity}
            data-testid="found-settlement-submit"
          >
            {busy ? 'Procesando…' : `Fundar ${selectedType === 'camp' ? 'campamento' : 'ciudad'}`}
          </button>
        </form>

        <div className="space-y-4">
          <div className="card p-5">
            <h2 className="text-xl text-yellow-100">Cómo conseguir puntos</h2>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex items-center justify-between rounded bg-gray-900/60 p-3">
                <span>⛪ Iglesia</span>
                <span className="font-bold text-yellow-300">+{status?.points_per_completion?.church ?? 1} / nivel</span>
              </div>
              <div className="flex items-center justify-between rounded bg-gray-900/60 p-3">
                <span>🕍 Catedral</span>
                <span className="font-bold text-yellow-300">+{status?.points_per_completion?.cathedral ?? 3} / nivel</span>
              </div>
            </div>
          </div>

          <div className="card p-5">
            <h2 className="text-xl text-yellow-100">Promoción de campamento</h2>
            <p className="mt-1 text-sm text-gray-400">
              La promoción cuesta exactamente la diferencia entre fundar un campamento y una ciudad directamente.
            </p>
            <div className="mt-3 flex items-center justify-between gap-3 text-sm">
              <span className="text-gray-300">Puntos</span>
              <span className="font-bold text-yellow-300">✦ {status?.camp_promotion_point_cost ?? 0}</span>
            </div>
            <div className="mt-2"><CostLine cost={status?.camp_promotion_cost} /></div>
          </div>
        </div>
      </section>

      <section className="card p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-xl text-yellow-100">Tus campamentos</h2>
            <p className="text-sm text-gray-400">Transporta recursos al campamento antes de promoverlo.</p>
          </div>
          <span className="badge">{camps.length}</span>
        </div>

        {camps.length === 0 ? (
          <p className="mt-4 rounded border border-dashed border-gray-700 p-5 text-center text-sm text-gray-500">
            Todavía no tienes campamentos.
          </p>
        ) : (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {camps.map((camp) => (
              <article key={camp.id} className="rounded border border-gray-700 bg-gray-900/50 p-4" data-testid={`camp-${camp.id}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-bold text-amber-100">⛺ {camp.name}</h3>
                    <p className="text-xs text-gray-500">({camp.x}, {camp.y}) · Población {camp.population_max}</p>
                  </div>
                  <button
                    type="button"
                    className="btn-primary px-3 py-2 text-xs"
                    disabled={busy}
                    onClick={() => handlePromote(camp.id)}
                    data-testid={`promote-camp-${camp.id}`}
                  >
                    Promover
                  </button>
                </div>
                <div className="mt-3"><CostLine cost={camp} /></div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};

export default ExpansionView;
