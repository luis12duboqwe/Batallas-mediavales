import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';

const RESEARCH_COSTS = {
    "basic_infantry": { wood: 0, clay: 0, iron: 0 },
    "heavy_infantry": { wood: 1000, clay: 800, iron: 800 },
    "archer": { wood: 1200, clay: 1000, iron: 1000 },
    "fast_cavalry": { wood: 2000, clay: 1500, iron: 1500 },
    "heavy_cavalry": { wood: 4000, clay: 3000, iron: 3000 },
    "spy": { wood: 500, clay: 500, iron: 500 },
    "ram": { wood: 3000, clay: 2000, iron: 1500 },
    "catapult": { wood: 4000, clay: 3000, iron: 3000 },
    "noble": { wood: 10000, clay: 10000, iron: 10000 },
};

const UNIT_REQUIREMENTS = {
    "basic_infantry": { "barracks": 1 },
    "heavy_infantry": { "barracks": 3, "smithy": 1 },
    "archer": { "barracks": 5, "smithy": 3 },
    "fast_cavalry": { "stable": 1 },
    "heavy_cavalry": { "stable": 5, "smithy": 5 },
    "spy": { "stable": 1 },
    "ram": { "workshop": 1 },
    "catapult": { "workshop": 5 },
    "noble": { "town_hall": 20, "workshop": 10 },
};

const AcademyView = () => {
    const { t } = useTranslation();
    const { currentCity, fetchCityStatus } = useCityStore();
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');

    const handleResearch = async (unitType) => {
        if (!currentCity) return;
        setLoading(true);
        setMessage('');
        try {
            await api.researchUnit(currentCity.id, currentCity.world_id, unitType);
            setMessage(`Investigación de ${t(unitType)} completada`);
            fetchCityStatus(currentCity.id, currentCity.world_id);
        } catch (error) {
            setMessage(error.response?.data?.detail || 'Error en investigación');
        } finally {
            setLoading(false);
        }
    };

    const checkRequirements = (unitType) => {
        if (!currentCity || !currentCity.buildings) return false;
        const reqs = UNIT_REQUIREMENTS[unitType] || {};
        for (const [buildingName, level] of Object.entries(reqs)) {
            const building = currentCity.buildings.find(b => b.name === buildingName);
            if (!building || building.level < level) {
                return false;
            }
        }
        return true;
    };

    const getMissingRequirements = (unitType) => {
        if (!currentCity || !currentCity.buildings) return [];
        const reqs = UNIT_REQUIREMENTS[unitType] || {};
        const missing = [];
        for (const [buildingName, level] of Object.entries(reqs)) {
            const building = currentCity.buildings.find(b => b.name === buildingName);
            if (!building || building.level < level) {
                missing.push(`${t(buildingName)} Nvl ${level}`);
            }
        }
        return missing;
    };

    const researchedUnits = currentCity?.researched_units || ["basic_infantry"];

    return (
        <div className="p-4 max-w-6xl mx-auto">
            <h2 className="text-3xl font-bold mb-6 text-amber-500">Academia Militar</h2>
            {message && <div className={`alert mb-4 ${message.includes('Error') ? 'alert-error' : 'alert-success'}`}>{message}</div>}
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {Object.entries(RESEARCH_COSTS).map(([unit, cost]) => {
                    const isResearched = researchedUnits.includes(unit);
                    const canResearch = checkRequirements(unit);
                    const missingReqs = getMissingRequirements(unit);
                    
                    // Check resources
                    const hasResources = currentCity && 
                        currentCity.wood >= cost.wood && 
                        currentCity.clay >= cost.clay && 
                        currentCity.iron >= cost.iron;

                    return (
                        <div key={unit} className={`bg-gray-800 border ${isResearched ? 'border-green-600' : 'border-gray-600'} p-5 rounded-lg shadow-lg relative overflow-hidden`}>
                            {isResearched && (
                                <div className="absolute top-0 right-0 bg-green-600 text-white text-xs px-2 py-1 rounded-bl">
                                    Investigado
                                </div>
                            )}
                            
                            <h3 className="font-bold text-xl text-amber-100 mb-2">{t(unit)}</h3>
                            
                            <div className="text-sm text-gray-400 mb-4">
                                <div className="flex gap-2 mb-1">
                                    <span className={currentCity?.wood < cost.wood ? 'text-red-400' : 'text-green-400'}>🪵 {cost.wood}</span>
                                    <span className={currentCity?.clay < cost.clay ? 'text-red-400' : 'text-green-400'}>🧱 {cost.clay}</span>
                                    <span className={currentCity?.iron < cost.iron ? 'text-red-400' : 'text-green-400'}>⛓️ {cost.iron}</span>
                                </div>
                            </div>

                            {!isResearched && missingReqs.length > 0 && (
                                <div className="mb-4 bg-red-900/30 p-2 rounded border border-red-900/50">
                                    <div className="text-xs text-red-300 font-bold mb-1">Requisitos faltantes:</div>
                                    <ul className="list-disc list-inside text-xs text-red-200">
                                        {missingReqs.map((req, idx) => <li key={idx}>{req}</li>)}
                                    </ul>
                                </div>
                            )}

                            {isResearched ? (
                                <button className="w-full bg-green-800/50 text-green-200 py-2 rounded cursor-default border border-green-700">
                                    Tecnología Dominada
                                </button>
                            ) : (
                                <button
                                    onClick={() => handleResearch(unit)}
                                    disabled={loading || !canResearch || !hasResources}
                                    className={`w-full py-2 rounded font-bold transition ${
                                        !canResearch || !hasResources
                                            ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                                            : 'bg-amber-600 hover:bg-amber-500 text-white'
                                    }`}
                                >
                                    {!canResearch ? 'Requisitos no cumplidos' : !hasResources ? 'Recursos insuficientes' : 'Investigar'}
                                </button>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default AcademyView;
