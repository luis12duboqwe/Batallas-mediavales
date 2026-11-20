import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { api } from '../../api/axiosClient';

const FIELDS = ['wood', 'stone', 'iron', 'gold'];
const NAMES = { wood: 'Madera', stone: 'Piedra', iron: 'Hierro', gold: 'Oro' };
const EMPTY = { wood: '', stone: '', iron: '', gold: '' };
const errorMessage = (error) => {
  const detail = error.response?.data?.detail;
  return typeof detail === 'string' ? detail : detail?.message || 'No se pudo realizar la operación.';
};

export default function WonderFundingPanel({ currentCity, refreshCity }) {
  const location = useLocation();
  const deepLink = Number(new URLSearchParams(location.search).get('targetCityId'));
  const [targetId, setTargetId] = useState(currentCity?.id ?? '');
  const [rules, setRules] = useState(null);
  const [fund, setFund] = useState(null);
  const [amounts, setAmounts] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const pending = useRef(null);

  useEffect(() => {
    setTargetId(Number.isSafeInteger(deepLink) && deepLink > 0 ? deepLink : (currentCity?.id ?? ''));
    setFund(null);
    setError('');
    setNotice('');
    setAmounts(EMPTY);
    pending.current = null;
  }, [currentCity?.id, currentCity?.world_id, deepLink]);

  useEffect(() => {
    let active = true;
    setRules(null);
    if (currentCity?.world_id) {
      // Normal players without an alliance cannot finance a Wonder. Avoid
      // issuing a forbidden funding request during routine Buildings visits.
      Promise.all([api.getWorlds(), api.getAlliance(currentCity.world_id)])
        .then(([worldResponse, allianceResponse]) => {
          if (!active) return;
          const pinned = worldResponse.data.find(
            (world) => world.id === currentCity.world_id,
          )?.wonder_rules_version;
          setRules(pinned === 'alliance-v2' && allianceResponse.data?.id
            ? 'alliance-v2' : 'legacy-v1');
        })
        .catch(() => {
          if (active) setError('No se pudieron verificar el mundo y la alianza.');
        });
    }
    return () => { active = false; };
  }, [currentCity?.world_id]);

  useEffect(() => {
    if (rules !== 'alliance-v2' || !currentCity?.world_id) return undefined;
    const cityId = Number(targetId);
    if (!Number.isSafeInteger(cityId) || cityId <= 0) {
      setFund(null);
      return undefined;
    }
    let active = true;
    setBusy(true);
    setError('');
    api.getWonderFunding(cityId, currentCity.world_id).then(({ data }) => {
      if (active) setFund(data);
    }).catch((err) => {
      if (active) { setFund(null); setError(errorMessage(err)); }
    }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [rules, targetId, currentCity?.world_id]);

  if (!currentCity || rules !== 'alliance-v2') return null;

  const send = async (event) => {
    event.preventDefault();
    if (!fund || busy) return;
    const payload = Object.fromEntries(FIELDS.map((key) => [key, Number(amounts[key] || 0)]));
    if (FIELDS.some((key) => !Number.isSafeInteger(payload[key]) || payload[key] < 0 || payload[key] > (fund.remaining[key] ?? 0))
      || !FIELDS.some((key) => payload[key] > 0)) {
      setError('Introduce cantidades enteras positivas sin superar el costo restante.');
      return;
    }
    const fingerprint = JSON.stringify({ targetId: fund.city_id, sourceId: currentCity.id, payload });
    if (pending.current?.fingerprint !== fingerprint) {
      pending.current = { fingerprint, key: crypto.randomUUID() };
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const { data } = await api.contributeWonder({
        worldId: currentCity.world_id, targetCityId: fund.city_id, sourceCityId: currentCity.id,
        amounts: payload, idempotencyKey: pending.current.key,
      });
      setFund(data);
      setAmounts(EMPTY);
      pending.current = null;
      setNotice('Aportación registrada. Los recursos quedan reservados para la Maravilla.');
      await refreshCity();
    } catch (err) {
      // Use the same request key on retry after an uncertain network failure.
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card p-5 space-y-4" aria-labelledby="wonder-funding-title" data-testid="wonder-funding-panel">
      <h2 id="wonder-funding-title" className="text-xl text-yellow-200">Fondo de Maravilla de alianza</h2>
      <p className="text-sm text-gray-300">
        Los miembros pueden aportar desde su ciudad a una Maravilla aliada. Los depósitos quedan vinculados
        permanentemente a esa ciudad, propietario y alianza: no son reembolsables.
      </p>
      <label className="block text-sm" htmlFor="wonder-target">ID de ciudad aliada
        <input id="wonder-target" type="number" min="1" step="1" value={targetId}
          className="block w-full bg-gray-900 border border-gray-600 rounded p-2 mt-1"
          onChange={(e) => { setTargetId(e.target.value); setFund(null); pending.current = null; }} />
      </label>
      {busy && <p role="status">Consultando financiación…</p>}
      {error && <p role="alert" className="text-red-200">{error}</p>}
      {notice && <p role="status" className="text-green-200">{notice}</p>}
      {fund && (
        <div className="space-y-3">
          <p className="text-sm">Nivel {fund.target_level} de 100 · {fund.status} · Construcción {fund.build_time} segundos</p>
          <div className="grid grid-cols-2 gap-2">
            {FIELDS.map((key) => (
              <div className="rounded border border-gray-700 p-2 text-sm" key={key}>
                <strong>{NAMES[key]}:</strong> {fund.funded[key] ?? 0}/{fund.cost[key] ?? 0}
                <span className="block text-gray-400">Restan {fund.remaining[key] ?? 0}</span>
              </div>
            ))}
          </div>
          {fund.status === 'funding' && (
            <form className="space-y-3" onSubmit={send}>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {FIELDS.map((key) => (
                  <label key={key} className="text-sm">{NAMES[key]}
                    <input type="number" min="0" step="1" max={fund.remaining[key] ?? 0}
                      value={amounts[key]}
                      onChange={(e) => {
                        setAmounts((prev) => ({ ...prev, [key]: e.target.value }));
                        pending.current = null;
                      }}
                      className="block w-full bg-gray-900 border border-gray-600 rounded p-2 mt-1" />
                  </label>
                ))}
              </div>
              <button className="btn-primary" type="submit" disabled={busy}>Aportar recursos</button>
            </form>
          )}
          {fund.can_queue && <p role="status" className="text-green-200">Financiación completa. El propietario puede iniciar la obra.</p>}
          {fund.status === 'queued' && <p role="status">La construcción está en curso.</p>}
        </div>
      )}
    </section>
  );
}
