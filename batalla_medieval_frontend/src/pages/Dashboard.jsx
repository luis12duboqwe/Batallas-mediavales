import { useEffect } from 'react';
import CityView from './CityView';
import { useUserStore } from '../store/userStore';

const Dashboard = () => {
  const { user, refreshCity } = useUserStore();

  useEffect(() => {
    refreshCity().catch(() => {});
  }, [refreshCity]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl">Ciudad de {user?.username}</h1>
        <p className="text-gray-400">Gestiona tus construcciones y tropas</p>
      </div>
      <CityView />
    </div>
  );
};

export default Dashboard;
