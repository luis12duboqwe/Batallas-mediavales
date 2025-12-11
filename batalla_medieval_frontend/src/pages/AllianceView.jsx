import { useEffect } from 'react';
import AllianceCard from '../components/AllianceCard';
import { useCityStore } from '../store/cityStore';

const AllianceView = () => {
  const { alliance, loadAlliance } = useCityStore();

  useEffect(() => {
    loadAlliance().catch(() => {});
  }, [loadAlliance]);

  const handleCreate = async (name) => {
    // Placeholder for API call
    console.log('create alliance', name);
  };

  const handleJoin = async (code) => {
    console.log('join alliance', code);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Alianza</h1>
          <p className="text-gray-400">Coordina con otros señores</p>
        </div>
      </div>
      <AllianceCard alliance={alliance} onCreate={handleCreate} onJoin={handleJoin} />
    </div>
  );
};

export default AllianceView;
