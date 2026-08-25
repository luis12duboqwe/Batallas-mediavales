import { useCallback, useEffect, useMemo, useState } from 'react';

import heroApi from '../api/heroApi';
import { useCityStore } from '../store/cityStore';

const SLOT_LABELS = {
  head: 'Cabeza',
  body: 'Cuerpo',
  feet: 'Pies',
  weapon: 'Arma',
  horse: 'Montura',
  artifact: 'Artefacto',
};

const BONUS_LABELS = {
  attack: 'experiencia de aventura',
  defense: 'reducción de daño',
  production: 'botín de recursos',
  speed: 'reducción de duración',
  loot: 'botín de recursos',
};

const errorMessage = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  return fallback;
};

const percent = (value) => `${Math.round(Number(value || 0) * 100)}%`;

const HeroView = () => {
  const { currentCity, loadCity } = useCityStore();
  const worldId = currentCity?.world_id ?? null;
  const [hero, setHero] = useState(null);
  const [items, setItems] = useState([]);
  const [rules, setRules] = useState(null);
  const [points, setPoints] = useState({ attack: 0, defense: 0, production: 0 });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    if (!worldId) return;
    setLoading(true);
    setError('');
    try {
      const [heroResponse, itemResponse, balanceResponse] = await Promise.all([
        heroApi.getHero(worldId),
        heroApi.getItems(worldId),
        heroApi.getRules(),
      ]);
      setHero(heroResponse.data);
      setItems(itemResponse.data || []);
      setRules(balanceResponse.data?.hero_package || null);
    } catch (requestError) {
      setError(errorMessage(requestError, 'No se pudo cargar el paquete del héroe.'));
    } finally {
      setLoading(false);
    }
  }, [worldId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const pendingTotal = points.attack + points.defense + points.production;
  const remainingPoints = Math.max((hero?.available_points || 0) - pendingTotal, 0);
  const slots = rules?.item_slots || Object.keys(SLOT_LABELS);
  const equipped = useMemo(
    () => new Map(items.filter((item) => item.is_equipped).map((item) => [item.slot, item])),
    [items],
  );
  const inventory = items.filter((item) => !item.is_equipped);

  const run = async (operation, fallback) => {
    setBusy(true);
    setError('');
    try {
      await operation();
    } catch (requestError) {
      setError(errorMessage(requestError, fallback));
    } finally {
      setBusy(false);
    }
  };

  const handleDistribute = () => run(async () => {
    const response = await heroApi.distributePoints(worldId, points);
    setHero(response.data);
    setPoints({ attack: 0, defense: 0, production: 0 });
  }, 'No se pudieron asignar los puntos.');

  const handleRevive = () => run(async () => {
    const response = await heroApi.revive(worldId);
    setHero(response.data);
    await loadCity();
  }, 'No se pudo reanimar al héroe.');

  const handleEquip = (itemId) => run(async () => {
    const response = await heroApi.equipItem(worldId, itemId);
    setItems(response.data || []);
    const heroResponse = await heroApi.getHero(worldId);
    setHero(heroResponse.data);
  }, 'No se pudo equipar el objeto.');

  const handleUnequip = (itemId) => run(async () => {
    const response = await heroApi.unequipItem(worldId, itemId);
    setItems(response.data || []);
    const heroResponse = await heroApi.getHero(worldId);
    setHero(heroResponse.data);
  }, 'No se pudo retirar el objeto.');

  if (!worldId) return <div role="status">Cargando ciudad activa...</div>;
  if (loading) return <div role="status">Cargando héroe...</div>;
  if (!hero) return <div role="alert" className="alert alert-error">{error || 'Héroe no disponible.'}</div>;

  const xpProgress = hero.next_level_xp > 0
    ? Math.min(100, Math.round((hero.xp / hero.next_level_xp) * 100))
    : 100;
  const reviveResource = Object.keys(hero.revive_cost || {})[0] || 'gold';
  const reviveAmount = Number(hero.revive_cost?.[reviveResource] || 0);

  return (
    <div
      className="p-3 sm:p-6 max-w-6xl mx-auto pb-24 md:pb-12 text-gray-100"
      data-testid="hero-package"
      data-rules-version={hero.rules_version}
    >
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3 mb-6">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-amber-300">Paquete de héroe</p>
          <h1 className="text-3xl font-bold text-amber-500">{hero.name}</h1>
        </div>
        <div className="text-xs text-gray-400 font-mono" data-testid="hero-rules-version">
          Reglas {hero.rules_version}
        </div>
      </div>

      {error && <div role="alert" className="alert alert-error mb-4">{error}</div>}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="space-y-6">
          <section className="card bg-black/40 border border-amber-900/40 p-5">
            <div className="flex justify-between items-center gap-3 mb-4">
              <h2 className="font-bold text-xl">Nivel {hero.level}</h2>
              <span className={`badge ${hero.status === 'dead' ? 'badge-error' : hero.status === 'adventure' ? 'badge-warning' : 'badge-success'}`} data-testid="hero-status">
                {hero.status === 'dead' ? 'Caído' : hero.status === 'adventure' ? 'En aventura' : 'En casa'}
              </span>
            </div>
            <div className="mb-4">
              <div className="flex justify-between text-sm mb-1"><span>Experiencia</span><span>{hero.xp} / {hero.next_level_xp || 'MAX'}</span></div>
              <progress className="progress progress-info w-full" value={xpProgress} max="100" />
            </div>
            <div className="mb-4">
              <div className="flex justify-between text-sm mb-1"><span>Salud</span><span>{Math.round(hero.health)}%</span></div>
              <progress className="progress progress-error w-full" value={hero.health} max="100" />
            </div>
            {hero.status === 'dead' && (
              <button type="button" className="btn btn-warning w-full" onClick={handleRevive} disabled={busy} data-testid="hero-revive">
                Reanimar por {reviveAmount} {reviveResource === 'gold' ? 'oro' : reviveResource}
              </button>
            )}
          </section>

          <section className="card bg-black/40 border border-amber-900/40 p-5" data-testid="hero-attributes">
            <h2 className="font-bold text-xl text-amber-200 mb-2">Atributos</h2>
            <p className="text-sm text-gray-400 mb-4">Puntos disponibles: <strong className="text-white">{remainingPoints}</strong></p>
            {[['attack', 'Ataque', 'Más experiencia en aventuras'], ['defense', 'Defensa', 'Menos daño en aventuras'], ['production', 'Logística', 'Más botín de recursos']].map(([key, label, description]) => (
              <div key={key} className="py-3 border-t border-white/10 first:border-t-0">
                <div className="flex items-center justify-between gap-3">
                  <div><div className="font-semibold">{label}</div><div className="text-xs text-gray-500">{description}</div></div>
                  <div className="flex items-center gap-2">
                    <button type="button" className="btn btn-xs" onClick={() => setPoints((value) => ({ ...value, [key]: Math.max(value[key] - 1, 0) }))} disabled={busy || points[key] === 0}>−</button>
                    <span className="min-w-8 text-center font-mono">{hero[`${key}_points`] + points[key]}</span>
                    <button type="button" className="btn btn-xs" onClick={() => setPoints((value) => ({ ...value, [key]: value[key] + 1 }))} disabled={busy || remainingPoints <= 0}>+</button>
                  </div>
                </div>
              </div>
            ))}
            {pendingTotal > 0 && <button type="button" className="btn btn-success w-full mt-4" onClick={handleDistribute} disabled={busy}>Guardar atributos</button>}
          </section>

          <section className="card bg-black/40 border border-amber-900/40 p-5" data-testid="hero-bonuses">
            <h2 className="font-bold text-xl text-amber-200 mb-3">Efectos activos</h2>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between"><dt>Experiencia</dt><dd>+{percent(hero.bonuses?.attack)}</dd></div>
              <div className="flex justify-between"><dt>Reducción de daño</dt><dd>{percent(hero.bonuses?.defense)}</dd></div>
              <div className="flex justify-between"><dt>Botín por atributo</dt><dd>+{percent(hero.bonuses?.production)}</dd></div>
              <div className="flex justify-between"><dt>Velocidad</dt><dd>{percent(hero.bonuses?.speed)}</dd></div>
              <div className="flex justify-between"><dt>Botín por objetos</dt><dd>+{percent(hero.bonuses?.loot)}</dd></div>
            </dl>
          </section>
        </div>

        <section className="card bg-black/40 border border-amber-900/40 p-5">
          <h2 className="font-bold text-xl text-amber-200 mb-4">Equipo</h2>
          <div className="space-y-3">
            {slots.map((slot) => {
              const item = equipped.get(slot);
              return (
                <div key={slot} className="rounded-lg border border-white/10 bg-black/30 p-3" data-testid={`hero-slot-${slot}`}>
                  <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">{SLOT_LABELS[slot] || slot}</div>
                  {item ? (
                    <div className="flex items-center justify-between gap-3">
                      <div><div className="font-semibold text-amber-100">{item.name}</div><div className="text-xs text-green-400">+{percent(item.bonus_value)} {BONUS_LABELS[item.bonus_type] || item.bonus_type}</div></div>
                      <button type="button" className="btn btn-xs btn-error" onClick={() => handleUnequip(item.id)} disabled={busy}>Quitar</button>
                    </div>
                  ) : <div className="text-gray-500 text-sm">Vacío</div>}
                </div>
              );
            })}
          </div>
        </section>

        <section className="card bg-black/40 border border-amber-900/40 p-5">
          <h2 className="font-bold text-xl text-amber-200 mb-2">Inventario</h2>
          <p className="text-xs text-gray-500 mb-4">Los objetos se obtienen mediante aventuras. Solo uno por slot puede estar equipado.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-1 gap-3">
            {inventory.map((item) => (
              <article key={item.id} className="rounded-lg border border-white/10 bg-black/30 p-3" data-testid="hero-item">
                <div className="flex justify-between gap-2"><strong className="text-amber-100">{item.name}</strong><span className="text-xs capitalize text-purple-300">{item.rarity}</span></div>
                <div className="text-xs text-gray-400 mt-1">{SLOT_LABELS[item.slot] || item.slot} · +{percent(item.bonus_value)} {BONUS_LABELS[item.bonus_type] || item.bonus_type}</div>
                <p className="text-xs text-gray-500 mt-2">{item.description}</p>
                <button type="button" className="btn btn-sm btn-primary w-full mt-3" onClick={() => handleEquip(item.id)} disabled={busy}>Equipar</button>
              </article>
            ))}
            {inventory.length === 0 && <div className="text-gray-500 text-sm italic">No hay objetos sin equipar.</div>}
          </div>
        </section>
      </div>
    </div>
  );
};

export default HeroView;
